// port of mol2chemfigPy3/bond.py
//
// The original reads bond stereo/order codes from Indigo's enum
// (Indigo.UP / Indigo.DOWN / Indigo.EITHER, plus raw ints 1-4 for bond
// order). Per the porting blueprint, those become plain integers here.
// We use the standard MDL V2000 molfile bond-stereo flags directly (1 =
// wedge up, 6 = wedge down, 4 = either/wavy) since that's exactly what our
// RDKit.js molblock adapter parses -- no translation layer needed.
//
// NB: bond order 4 ("aromatic") and stereo flag 4 ("either") are different
// molfile columns, so they don't collide in practice -- but they *would*
// collide if merged into a single lookup object (this is what the upstream
// Python `bond_mapping` dict does, keyed by both order ints and Indigo's
// stereo enum; if Indigo.EITHER ever equalled 4 that dict would silently
// mis-resolve). We avoid the ambiguity entirely by keeping order and
// stereo name lookups in two separate tables.
export const STEREO = { UP: 1, DOWN: 6, EITHER: 4 };

const BOND_ORDER_NAMES = { 1: "single", 2: "double", 3: "triple", 4: "aromatic" };
const BOND_STEREO_NAMES = {
  [STEREO.UP]: "upto",
  [STEREO.DOWN]: "downto",
  [STEREO.EITHER]: "either",
};

import { pyRound, pyMod, rjust } from "./common.js";
import * as cfm from "./chemfigMappings.js";

export function comparePositions(x1, y1, x2, y2) {
  const xDiff = x2 - x1;
  const yDiff = y2 - y1;

  const length = Math.sqrt(xDiff ** 2 + yDiff ** 2);

  let angle;
  if (xDiff === 0) {
    angle = yDiff < 0 ? 270 : 90;
  } else {
    const rawAngle = (Math.atan(Math.abs(yDiff / xDiff)) * 180) / Math.PI;

    if (yDiff >= 0) {
      angle = xDiff > 0 ? rawAngle : 180 - rawAngle;
    } else {
      angle = xDiff > 0 ? -rawAngle : 180 + rawAngle;
    }
  }

  return [length, angle];
}

// a bond connects two atoms and computes its angle and length from those.
// It knows how to render itself to chemfig. Bonds can be hooks.
export class Bond {
  isLast = false; // flag for bond that is the last descendant of the exit
  // bond - needed in rare cases for bond formatting.
  toPhantom = false; // flag for bonds that should render their end atoms
  // as phantoms: ring closures and cross bonds
  isTrunk = false; // by default, bonds are not part of the trunk
  parent = null; // will be assigned when bonds are added to the tree.
  clockwise = 0; // only significant in double bonds in rings that are
  // not drawn with aromatic circles

  // `bare: true` skips all atom-dependent computation, for subclasses
  // (DummyFirstBond, AromaticRingBond) that build their own state instead
  // of calling through the regular Bond constructor -- mirrors how the
  // Python subclasses simply don't call Bond.__init__.
  constructor(options, startAtom, endAtom, bondType = null, stereo = 0, { bare = false } = {}) {
    this.options = options;
    this.startAtom = startAtom;
    this.endAtom = endAtom;

    // special styles that get rendered via tikz
    this.tikzStyles = new Set();
    this.tikzValues = {};

    if (bare) return;

    if (stereo === STEREO.UP || stereo === STEREO.DOWN) {
      if (this.options.flip_vertical !== this.options.flip_horizontal) {
        stereo = STEREO.UP + STEREO.DOWN - stereo;
      }
    }

    if (stereo === STEREO.UP || stereo === STEREO.DOWN || stereo === STEREO.EITHER) {
      // implies single bond
      this.bondType = BOND_STEREO_NAMES[stereo];
    } else {
      // no interesting stereo property - simply go with bond valence
      // or else keep passed-in string specifier
      this.bondType = BOND_ORDER_NAMES[bondType] ?? bondType;
    }

    // bonds now are also the nodes in the molecule tree. These two
    // attributes must be set later, when the tree is created.
    this.descendants = [];

    const [length, rawAngle] = this.bondDimensions();
    this.length = length; // adjusted and rounded later, after all is parsed

    // apply molecule rotation
    this.angle = rawAngle + this.options.rotate;

    // define marker
    const marker = this.options.markers ?? null;
    if (marker !== null) {
      const ids = [this.startAtom.idx + 1, this.endAtom.idx + 1].sort((a, b) => a - b);
      this.marker = `${marker}${ids[0]}-${ids[1]}`;
    } else {
      this.marker = "";
    }
  }

  bondDimensions() {
    return comparePositions(this.startAtom.x, this.startAtom.y, this.endAtom.x, this.endAtom.y);
  }

  // determine whether the bond will be drawn clockwise or counterclockwise
  // relative to center
  isClockwise(centerX, centerY) {
    if (this.clockwise) return; // assign only once

    const [, centerAngleRaw] = comparePositions(this.endAtom.x, this.endAtom.y, centerX, centerY);

    // bond is already rotated at this stage, so we need to rotate the
    // ring center also
    const centerAngle = centerAngleRaw + this.options.rotate;
    const centerKink = pyMod(centerAngle - this.angle, 360);

    this.clockwise = centerKink > 180 ? 1 : -1;
  }

  // shallow copy but keep original atoms (matches Python's copy.copy(); the
  // caller of clone() always resets .descendants right after anyway)
  clone() {
    return Object.assign(Object.create(Object.getPrototypeOf(this)), this);
  }

  // draw a bond backwards.
  invert() {
    const c = Object.assign(Object.create(Object.getPrototypeOf(this)), this);
    c.descendants = [];
    c.tikzStyles = new Set(this.tikzStyles);
    c.tikzValues = { ...this.tikzValues };

    c.startAtom = this.endAtom;
    c.endAtom = this.startAtom;
    c.angle = pyMod(this.angle + 180, 360);

    if (this.bondType === "upto") {
      c.bondType = "upfrom";
    } else if (this.bondType === "downto") {
      c.bondType = "downfrom";
    }

    return c;
  }

  // make this bond an invisible link. this also cancels any other tikz
  // styles, and removes the marker.
  setLink() {
    this.bondType = "link";
    this.tikzStyles = new Set();
    this.tikzValues = {};
    this.marker = "";
  }

  // draw this bond crossing over another.
  setCross(last = false) {
    const startAngles = this.upstreamAngles();
    const endAngles = this.downstreamAngles();

    const startAngle = Math.min(startAngles.left, startAngles.right);
    const start = Math.max(10, Bond.cotan100(startAngle));

    const endAngle = Math.min(endAngles.left, endAngles.right);
    const end = Math.max(10, Bond.cotan100(endAngle));

    this.tikzStyles.add("cross");
    this.tikzValues.bgstart = start;
    this.tikzValues.bgend = end;

    this.isLast = last;
  }

  // determine the narrowest upstream or downstream angles on the left and
  // the right.
  _adjoiningAngles(atom, inversionAngle = 0) {
    let rawAngles = atom.bondAngles.map((a) => pyMod(pyRound(a, 0), 360));

    const referenceAngle = pyMod(pyRound(this.angle - inversionAngle, 0), 360);

    const idx = rawAngles.indexOf(referenceAngle);
    if (idx === -1) {
      throw new Error(`angle ${referenceAngle} not found among atom's bond_angles`);
    }
    rawAngles.splice(idx, 1);

    if (rawAngles.length === 0) {
      // no other bonds attach to start atom
      return [null, null];
    }

    const angles = rawAngles.map((a) => pyMod(a - referenceAngle, 360)).sort((a, b) => a - b);

    return [pyRound(angles[0], 0), pyRound(angles[angles.length - 1], 0)];
  }

  // determine the narrowest upstream left and upstream right angle.
  upstreamAngles() {
    let [first, last] = this._adjoiningAngles(this.startAtom);
    // for the right angle, convert outer to inner
    if (last !== null) last = 360 - last;
    return { left: first, right: last };
  }

  // determine the narrowest downstream left and downstream right angle.
  downstreamAngles() {
    let [first, last] = this._adjoiningAngles(this.endAtom, 180);
    if (last !== null) {
      // for the left angle, convert outer to inner
      last = 360 - last;
    }
    return { left: last, right: first };
  }

  // scoring function used in picking sides for second stroke of double bond
  static anglePenalty(angle) {
    if (angle === null || angle === undefined) return 0;
    return (angle - 105) ** 2;
  }

  // 100 times cotan of angle, rounded
  static cotan100(angle) {
    const tan = Math.tan((angle * Math.PI) / 180);
    return pyRound(100 / tan, 0);
  }

  // determine by how much to shorten the second stroke of a double bond.
  shortenStroke(sameAngle, otherAngle) {
    if (sameAngle === null) return 0; // other_angle will be, too; don't shorten.

    let angle;
    if (sameAngle <= 180) {
      angle = 0.5 * sameAngle;
    } else if (sameAngle > 210 && sameAngle < 270) {
      angle = sameAngle - 180;
    } else if (otherAngle !== null && otherAngle > 210 && otherAngle < 270) {
      angle = otherAngle - 180;
    } else {
      angle = 90;
    }

    return Bond.cotan100(angle);
  }

  // work out the parameters for rendering a fancy double bond: which side
  // the second stroke goes on, and by how much to shorten start/end.
  fancyDouble() {
    const startAngles = this.upstreamAngles();
    const endAngles = this.downstreamAngles();

    // outside rings and if the double bond connects to explicit atoms,
    // plain symmetric double bonds tend to look better.
    if (!this.clockwise && (this.startAtom.explicit || this.endAtom.explicit)) {
      if (this.startAtom.explicit && this.endAtom.explicit) {
        return null;
      }
      if (
        this.startAtom.explicit &&
        (endAngles.left === null ||
          (Math.abs(endAngles.left) >= 90 &&
            Math.abs(endAngles.left) <= 135 &&
            Math.abs(endAngles.right) >= 90 &&
            Math.abs(endAngles.right) <= 135))
      ) {
        return null;
      }
      if (
        this.endAtom.explicit &&
        (startAngles.left === null ||
          (Math.abs(startAngles.left) >= 90 &&
            Math.abs(startAngles.left) <= 135 &&
            Math.abs(startAngles.right) >= 90 &&
            Math.abs(startAngles.right) <= 135))
      ) {
        return null;
      }
    }

    // at this point we are looking at either only implicit atoms or
    // extreme angles.
    let side;
    if (this.clockwise === -1) {
      side = "left";
    } else if (this.clockwise === 1) {
      side = "right";
    } else {
      // not in a ring. use scoring function to pick sides.
      const ap = Bond.anglePenalty;
      const leftPenalty = ap(startAngles.left) + ap(endAngles.left);
      const rightPenalty = ap(startAngles.right) + ap(endAngles.right);

      if (leftPenalty < rightPenalty) {
        side = "left";
      } else if (leftPenalty > rightPenalty) {
        side = "right";
      } else {
        // penalties equal - try to pick sides consistently
        side = Math.abs(this.angle - 44.5) < 90 ? "left" : "right";
      }
    }

    let start;
    if (this.startAtom.explicit) {
      start = 0;
    } else if (side === "left") {
      start = this.shortenStroke(startAngles.left, startAngles.right);
    } else {
      start = this.shortenStroke(startAngles.right, startAngles.left);
    }

    let end;
    if (this.endAtom.explicit) {
      end = 0;
    } else if (side === "left") {
      end = this.shortenStroke(endAngles.left, endAngles.right);
    } else {
      end = this.shortenStroke(endAngles.right, endAngles.left);
    }

    return [side, start, end];
  }

  // work out parameters for fancy triple bond. No side choice needed, just
  // the required line shortening.
  fancyTriple() {
    let start;
    if (this.startAtom.explicit) {
      start = 0;
    } else {
      const startAngles = Object.values(this.upstreamAngles());
      start = startAngles[0] !== null ? Bond.cotan100(0.5 * Math.min(...startAngles)) : 0;
    }

    let end;
    if (this.endAtom.explicit) {
      end = 0;
    } else {
      const endAngles = Object.values(this.downstreamAngles());
      end = endAngles[0] !== null ? Bond.cotan100(0.5 * Math.min(...endAngles)) : 0;
    }

    return [start, end];
  }

  // delegate to chemfig_mappings module to render the bond code, without
  // the atom
  bondToChemfig() {
    const endStringPos = this.toPhantom ? this.endAtom.phantomPos : this.endAtom.stringPos;

    if (this.options.fancy_bonds && (this.bondType === "double" || this.bondType === "triple")) {
      if (this.bondType === "double") {
        const fd = this.fancyDouble();
        if (fd !== null) {
          const [side, start, end] = fd;
          this.tikzStyles.add("double");
          this.tikzStyles.add(side);
          this.tikzValues.start = start;
          this.tikzValues.end = end;
          this.bondType = "decorated";
        }
      } else if (this.bondType === "triple") {
        this.tikzStyles.add("triple");
        const [start, end] = this.fancyTriple();
        this.tikzValues.start = start;
        this.tikzValues.end = end;
        this.bondType = "decorated";
      }
    }

    return cfm.formatBond(
      this.options,
      this.angle,
      this.parent.angle,
      this.bondType,
      this.clockwise,
      this.isLast,
      this.length,
      this.startAtom.stringPos,
      endStringPos,
      this.tikzStyles,
      this.tikzValues,
      this.marker,
    );
  }

  indent(level, bondCode, atomCode = "", commentCode = "") {
    let stuff = " ".repeat(this.options.indent * level) + rjust(bondCode, cfm.BOND_CODE_WIDTH) + atomCode;

    if (commentCode) {
      stuff += "% " + commentCode;
    }

    return stuff.trimEnd();
  }

  // render bond and trailing atom.
  render(level) {
    let atomCode, commentCode;
    if (!this.toPhantom) {
      [atomCode, commentCode] = this.endAtom.render();
    } else {
      [atomCode, commentCode] = this.endAtom.renderPhantom();
    }

    const bondCode = this.bondToChemfig();

    return this.indent(level, bondCode, atomCode, commentCode);
  }
}

// semi-dummy class that only takes an end-atom, which is the first atom in
// the molecule, and just renders that. The other dummy attributes only
// exist to play nice with the Molecule class.
export class DummyFirstBond extends Bond {
  constructor(options, endAtom) {
    super(options, null, endAtom, null, 0, { bare: true });
    this.angle = null;
    this.descendants = [];
    this.length = null;
  }

  // render an empty bond
  bondToChemfig() {
    return ""; // empty bond code before first atom
  }
}

// a gross hack to render the circle inside an aromatic ring as a node in
// the regular bond hierarchy.
export class AromaticRingBond extends Bond {
  static scale = 1.5; // 1.5 corresponds to ring size of chemfig

  constructor(options, parent, angle, length, innerR) {
    super(options, null, null, null, 0, { bare: true });
    this.descendants = [];

    this.angle = pyMod(cfm.numRound(angle, 1), 360);
    this.parentAngle = parent !== null ? parent.angle : null;
    this.length = cfm.numRound(length, 2);
    this.radius = cfm.numRound(AromaticRingBond.scale * innerR, 2);
  }

  // there is no atom to render, so we just call chemfig_mappings on our
  // own attributes.
  render(level) {
    const [ringBondCode, ringCode, comment] = cfm.formatAromaticRing(
      this.options,
      this.angle,
      this.parentAngle,
      this.length,
      this.radius,
    );

    return this.indent(level, ringBondCode, ringCode, comment);
  }
}

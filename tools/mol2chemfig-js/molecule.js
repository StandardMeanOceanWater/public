// port of mol2chemfigPy3/molecule.py
// parse an engine molecule (via the tkmol adapter, see molblockAdapter.js)
// and render to chemfig code.

import * as cfm from "./chemfigMappings.js";
import { MCFError, Counter, pyRound, rjust } from "./common.js";
import { Atom } from "./atom.js";
import { Bond, DummyFirstBond, AromaticRingBond, comparePositions } from "./bond.js";

const pairKey = (a, b) => `${a},${b}`;

export class Molecule {
  constructor(options, tkmol) {
    this.options = options;
    this.tkmol = tkmol;
    this.bondScale = 1.0; // can be overridden by user option
    this.exitBond = null; // the first bond in the tree that connects to the exit atom

    this.atoms = this.parseAtoms();

    // now it's time to flip and flop the coordinates
    for (const atom of this.atoms) {
      if (this.options.flip_horizontal) atom.x = -atom.x;
      if (this.options.flip_vertical) atom.y = -atom.y;
    }

    const [bonds, atomPairs] = this.parseBonds();
    this.bonds = bonds;
    this.atomPairs = atomPairs;

    // work out the angles for each atom - this is used for positioning of
    // implicit hydrogen and charges. (bond.startAtom.idx is always the
    // first element of whichever (start,end) key this entry lives under,
    // since the reverse-direction entries are already .invert()'d bonds.)
    for (const bond of this.bonds.values()) {
      this.atoms[bond.startAtom.idx].bondAngles.push(bond.angle);
    }

    // this would be the place to work out the placement of the second and
    // third strokes.

    // connect fragments, if any, with invisible bonds. By doing this
    // AFTER assigning bond angles, we prevent these invisible bonds from
    // interfering with placement of hydrogen or charges.
    this.connectFragments(); // connect fragments or isolated atoms

    // arrange the bonds into a tree
    this.seenAtoms = new Set();
    this.seenBonds = new Set();

    const [entryAtom, exitAtom] = this.pickFirstLastAtoms();
    this.entryAtom = entryAtom;
    this.exitAtom = exitAtom;
    this.root = this.parseTree(null, this.entryAtom);

    if (this.atoms.length > 1) {
      if (this.exitAtom === null) {
        // pick a default exit atom if needed
        this.exitBond = this.defaultExitBond();
        this.exitAtom = this.exitBond.endAtom;
      }

      // flag all atoms between the entry atom and the exit atom - these
      // will be part of the trunk, all others will be rendered as branches
      if (this.entryAtom !== this.exitAtom) {
        let flaggedBond = this.exitBond;
        while (flaggedBond.endAtom !== this.entryAtom) {
          flaggedBond.isTrunk = true;
          flaggedBond = flaggedBond.parent;
        }
      }

      // process cross bonds
      if (this.options.cross_bond !== null && this.options.cross_bond !== undefined) {
        this.processCrossBonds();
      }

      // adjust bond lengths
      this.scaleBonds();

      // modify bonds in rings
      this.annotateRings();
    }

    // let each atom work out its preferred quadrant for placing hydrogen
    // or charges
    for (const atom of this.atoms) {
      atom.scoreAngles();
    }

    // finally, render the thing and cache the result.
    this._rendered = this.render();
  }

  // connect atoms with indexes x and y using a pseudo bond. Helper for
  // connectFragments
  linkAtoms(x, y) {
    const startAtom = this.atoms[x];
    const endAtom = this.atoms[y];

    const bond = new Bond(this.options, startAtom, endAtom);
    bond.setLink();

    this.bonds.set(pairKey(x, y), bond);
    this.bonds.set(pairKey(y, x), bond.invert());

    startAtom.neighbors.push(y);
    endAtom.neighbors.push(x);
  }

  // connect multiple fragments, using link bonds across their last and
  // first atoms, respectively.
  connectFragments() {
    const fragments = this.moleculeFragments();

    if (fragments.length > 1) {
      for (let i = 0; i < fragments.length - 1; i++) {
        const head = fragments[i];
        const tail = fragments[i + 1];
        const headLast = head[head.length - 1][1];
        const tailFirst = tail[0][0];
        this.linkAtoms(headLast, tailFirst);
      }
    }

    // now look for orphaned single atoms
    const atoms = new Set(this.atoms.map((a) => a.idx));

    const bonded = new Set();
    for (const pair of this.atomPairs) {
      bonded.add(pair[0]);
      bonded.add(pair[1]);
    }

    let unBonded = [...atoms].filter((a) => !bonded.has(a));

    if (unBonded.length) {
      let anchor;
      if (fragments.length) {
        const lastFragment = fragments[fragments.length - 1];
        anchor = lastFragment[lastFragment.length - 1][1];
      } else {
        anchor = unBonded[0];
        unBonded = unBonded.slice(1);
      }

      for (const atom of unBonded) {
        this.linkAtoms(anchor, atom);
      }
    }
  }

  // identify unconnected fragments in the molecule. used by
  // connectFragments
  moleculeFragments() {
    const splitPairs = (pairList) => {
      const first = pairList[0];
      let rest = pairList.slice(1);
      const connectedAtoms = new Set(first);
      const connectedPairs = [first];

      while (true) {
        const unconnected = [];
        for (const r of rest) {
          if (r.some((x) => connectedAtoms.has(x))) {
            for (const x of r) connectedAtoms.add(x);
            connectedPairs.push(r);
          } else {
            unconnected.push(r);
          }
        }
        if (unconnected.length === rest.length) {
          return [connectedPairs, unconnected];
        }
        rest = unconnected;
      }
    };

    const fragments = [];
    let atomPairs = this.atomPairs.slice();

    if (atomPairs.length === 0) return [];
    if (atomPairs.length === 1) return [atomPairs];

    while (true) {
      const [connected, rest] = splitPairs(atomPairs);
      fragments.push(connected);
      if (!rest.length) return fragments;
      atomPairs = rest;
    }
  }

  // return a list with all bonds in the molecule tree
  treebonds(root = false) {
    const allBonds = [];
    const recurse = (rt) => {
      allBonds.push(rt);
      for (const d of rt.descendants) recurse(d);
    };
    recurse(this.root);
    return root ? allBonds : allBonds.slice(1);
  }

  // if cross bonds have been declared:
  // 1. tag the corresponding bonds within the tree as no-ops
  // 2. create a ghost-bond connection from exit_atom to start atom
  // 3. create a drawn duplicate of the cross bond
  // 4. append 2 and 3 as branch to the exit atom
  processCrossBonds() {
    const crossBonds = this.options.cross_bond;

    for (const [start1, end1] of crossBonds) {
      const start = start1 - 1;
      const end = end1 - 1;

      let bond = null;
      for (const [a, b] of [
        [start, end],
        [end, start],
      ]) {
        if (this.seenBonds.has(pairKey(a, b))) {
          bond = this.bonds.get(pairKey(a, b));
          break;
        }
      }
      if (bond === null) {
        throw new MCFError(`bond ${start1}-${end1} doesn't exist`);
      }

      // very special case: the bond _might_ already be the very last one
      // to be rendered - then we just tag it
      if (this.exitBond.descendants.length && bond === this.exitBond.descendants[this.exitBond.descendants.length - 1]) {
        bond.setCross(true);
        continue;
      }

      // create a copy of the bond that will be rendered later
      const bondCopy = bond.clone();

      // tag original bond as no-op
      bond.setLink();

      // modify bond copy
      bondCopy.setCross();
      bondCopy.toPhantom = true; // don't render atom again
      bondCopy.descendants = []; // forget copied descendants

      if (bondCopy.startAtom !== this.exitAtom) {
        // usual case
        // create a pseudo bond from the exit atom to the start atom
        // pseudo bond will not be drawn, serves only to "move the pen"
        const pseudoBond = new Bond(this.options, this.exitAtom, bondCopy.startAtom);

        pseudoBond.setLink();
        pseudoBond.toPhantom = true; // don't render the atom, either

        bondCopy.parent = pseudoBond;
        pseudoBond.descendants.push(bondCopy);

        pseudoBond.parent = this.exitBond;
        this.exitBond.descendants.push(pseudoBond);
      } else {
        // occasionally, the molecule's exit atom may be the starting
        // point of the elevated bond
        this.exitBond.descendants.push(bondCopy);
      }
    }
  }

  // pick the bond and atom that is at the greatest distance from the
  // entry atom along the parsed molecule tree. This must be one of the
  // leaf atoms, obviously.
  defaultExitBond() {
    const scored = [];
    for (const bond of this.treebonds()) {
      if (bond.toPhantom) continue; // don't pick phantom atoms as exit

      let distance = 0;
      let theBond = bond;
      while (theBond !== null && theBond.endAtom !== this.entryAtom) {
        distance += 1;
        theBond = theBond.parent;
      }

      scored.push([distance, bond.descendants.length, bond]);
    }
    scored.sort((a, b) => a[0] - b[0]);
    return scored[scored.length - 1][2];
  }

  // If the first atom is not given, we try to pick one that has only one
  // bond to the rest of the molecule, so that only the first angle is
  // absolute.
  pickFirstLastAtoms() {
    let entryAtom;
    if (this.options.entry_atom !== null && this.options.entry_atom !== undefined) {
      entryAtom = this.atoms[this.options.entry_atom - 1];
      if (entryAtom === undefined) throw new MCFError("Invalid entry atom number");
    } else {
      // pick a default atom with few neighbors
      const sorted = this.atoms.slice().sort((a, b) => a.neighbors.length - b.neighbors.length);
      entryAtom = sorted[0];
    }

    let exitAtom;
    if (this.options.exit_atom !== null && this.options.exit_atom !== undefined) {
      exitAtom = this.atoms[this.options.exit_atom - 1];
      if (exitAtom === undefined) throw new MCFError("Invalid exit atom number");
    } else {
      exitAtom = null;
    }

    return [entryAtom, exitAtom];
  }

  // Read some attributes from the toolkit atom object
  parseAtoms() {
    const wrappedAtoms = [];

    for (const ra of this.tkmol.iterateAtoms()) {
      const idx = ra.index();
      const element = ra.symbol();
      const hydrogens = ra.countImplicitHydrogens();
      const charge = ra.charge();
      const radical = ra.radicalElectrons();
      const neighbors = ra.iterateNeighbors().map((na) => na.index());
      const [x, y] = ra.xyz();

      wrappedAtoms[idx] = new Atom(this.options, idx, x, y, element, hydrogens, charge, radical, neighbors);
    }

    return wrappedAtoms;
  }

  // read some bond attributes
  parseBonds() {
    const bonds = new Map();
    const atomPairs = [];

    for (const tkBond of this.tkmol.iterateBonds()) {
      const start = tkBond.source().index();
      const end = tkBond.destination().index();

      const bondType = tkBond.bondOrder(); // 1,2,3,4 for single, double, triple, aromatic
      const stereo = tkBond.bondStereo();

      const startAtom = this.atoms[start];
      const endAtom = this.atoms[end];

      const bond = new Bond(this.options, startAtom, endAtom, bondType, stereo);

      // we store both orientations of the bond, since we don't know yet
      // which way it will be used
      bonds.set(pairKey(start, end), bond);
      bonds.set(pairKey(end, start), bond.invert());

      atomPairs.push([start, end]);
    }

    return [bonds, atomPairs];
  }

  // recurse over atoms in molecule to create a tree of bonds
  parseTree(startAtom, endAtom) {
    const endIdx = endAtom.idx;
    let startIdx = null;
    let bond;

    if (startAtom === null) {
      // this is the first atom in the molecule
      bond = new DummyFirstBond(this.options, endAtom);
    } else {
      startIdx = startAtom.idx;

      // guard against reentrant bonds.
      if (this.seenBonds.has(pairKey(startIdx, endIdx)) || this.seenBonds.has(pairKey(endIdx, startIdx))) {
        return null;
      }

      // if we get here, the bond is not in the tree yet
      bond = this.bonds.get(pairKey(startIdx, endIdx));

      // flag it as known
      this.seenBonds.add(pairKey(startIdx, endIdx));

      // detect bonds that close rings, and tell them render with
      // phantom atoms
      if (this.seenAtoms.has(endIdx)) {
        bond.toPhantom = true;
        return bond;
      }
    }

    // flag end atom as known
    this.seenAtoms.add(endIdx);

    if (endAtom === this.exitAtom) {
      this.exitBond = bond;
    }

    // recurse over the neighbors of the end atom
    for (const ni of endAtom.neighbors) {
      if (startAtom && ni === startIdx) continue; // don't recurse backwards

      const nextAtom = this.atoms[ni];
      const nextBond = this.parseTree(endAtom, nextAtom);

      if (nextBond !== null) {
        nextBond.parent = bond;
        bond.descendants.push(nextBond);
      }
    }

    return bond;
  }

  // helper for aromatizeRing: find bond in parse tree that corresponds to
  // toolkit bond
  _getBond(tkBond) {
    const startIdx = tkBond.source().index();
    const endIdx = tkBond.destination().index();

    if (this.seenBonds.has(pairKey(startIdx, endIdx))) {
      return this.bonds.get(pairKey(startIdx, endIdx));
    }

    // the bond must be going the other way ...
    return this.bonds.get(pairKey(endIdx, startIdx));
  }

  // render a ring that is aromatic and is a regular polygon
  aromatizeRing(ring, centerX, centerY) {
    // first, set all bonds to aromatic
    const ringBonds = ring.iterateBonds();
    let bond = null;
    for (const tkBond of ringBonds) {
      bond = this._getBond(tkBond);
      bond.bondType = "aromatic";
    }

    // any bond can serve as the anchor for the circle, so we'll just use
    // the last one from the loop
    const atom = bond.endAtom;

    let [outerR, angle] = comparePositions(atom.x, atom.y, centerX, centerY);
    // angle is based on raw coordinates - adjust for user-set rotation
    angle += this.options.rotate;

    // outer_r calculated from raw coordinates, must be adjusted for bond
    // scaling that may have taken place
    outerR *= this.bondScale;

    const alpha = Math.PI / 2 - Math.PI / ringBonds.length;
    const innerR = Math.sin(alpha) * outerR;

    const arb = new AromaticRingBond(this.options, bond, angle, outerR, innerR);
    bond.descendants.push(arb);
  }

  // determine center, symmetry and aromatic character of ring. annotate
  // double bonds in rings, or alternatively decorate ring with aromatic
  // circle.
  annotateRing(ring, isAromatic) {
    const atoms = new Set();
    const bondLengths = [];
    const bonds = [];

    for (const tkBond of ring.iterateBonds()) {
      const bond = this._getBond(tkBond);
      bonds.push(bond);

      atoms.add(this.atoms[bond.startAtom.idx]);
      atoms.add(this.atoms[bond.endAtom.idx]);
      bondLengths.push(bond.length);
    }

    if (bonds.length > 8) return; // large rings may foul things up, so we skip them.

    const blMax = Math.max(...bondLengths);
    const blSpread = (blMax - Math.min(...bondLengths)) / blMax;

    // determine ring center
    const atomList = [...atoms];
    const centerX = atomList.reduce((s, a) => s + a.x, 0) / atomList.length;
    const centerY = atomList.reduce((s, a) => s + a.y, 0) / atomList.length;

    // compare distances from center. Also remember atoms and bond angles;
    // if the ring ends up being aromatized, we flag those angles as
    // occupied (by the fancy circle inside the ring).
    const atomAngles = [];
    const centerDistances = [];

    for (const atom of atomList) {
      const [length, angle] = comparePositions(atom.x, atom.y, centerX, centerY);
      centerDistances.push(length);
      atomAngles.push([atom, angle]);
    }

    const cdMax = Math.max(...centerDistances);
    const cdSpread = (cdMax - Math.min(...centerDistances)) / cdMax;

    const tolerance = 0.05;
    const isSymmetric = cdSpread <= tolerance && blSpread <= tolerance;

    if (isAromatic && isSymmetric && this.options.aromatic_circles) {
      // ring meets all requirements to be displayed with circle inside
      this.aromatizeRing(ring, centerX, centerY);
      // flag bond angles as occupied
      for (const [atom, angle] of atomAngles) {
        atom.bondAngles.push(angle);
      }
    } else {
      // flag orientation individual bonds - will influence rendering of
      // double bonds
      for (const bond of bonds) {
        bond.isClockwise(centerX, centerY);
      }
    }
  }

  // modify double bonds in rings. In aromatic rings, we optionally do
  // away with double bonds altogether and draw a circle instead
  annotateRings() {
    this.tkmol.aromatize();

    const allRings = [];
    for (const ring of this.tkmol.iterateSSSR()) {
      // bond-order == 4 means "aromatic"; all rings bonds must be aromatic
      const isAromatic = ring.iterateBonds().every((bond) => bond.bondOrder() === 4);
      allRings.push([isAromatic, ring]);
    }

    // prefer aromatic rings to non-aromatic ones, so that double bonds on
    // fused rings go preferably into aromatic rings
    allRings.sort((a, b) => Number(a[0]) - Number(b[0]));

    for (let i = allRings.length - 1; i >= 0; i--) {
      const [isAromatic, ring] = allRings[i];
      this.annotateRing(ring, isAromatic);
    }
  }

  // scale bonds according to user options
  scaleBonds() {
    if (this.options.bond_scale === "keep") {
      // no-op
    } else if (this.options.bond_scale === "normalize") {
      const lengths = this.treebonds().map((bond) => pyRound(bond.length, this.options.bond_round));
      const counter = new Counter(lengths);
      this.bondScale = this.options.bond_stretch / counter.mostCommon();
    } else if (this.options.bond_scale === "scale") {
      this.bondScale = this.options.bond_stretch;
    }

    for (const bond of this.treebonds()) {
      bond.length = this.bondScale * bond.length;
    }
  }

  // render molecule to chemfig
  render() {
    const output = [];
    this._render(output, this.root, 0);
    return output;
  }

  // returns code formatted according to user options
  renderUser() {
    return cfm.formatOutput(this.options, this._rendered);
  }

  // returns code formatted for server-side PDF generation
  renderServer() {
    const params = { ...this.options, submol_name: null, chemfig_command: true };
    return cfm.formatOutput(params, this._rendered);
  }

  // render a list of branching bonds indented and inside enclosing brackets.
  _renderBranches(output, level, bonds) {
    const branchIndent = this.options.indent;

    for (const bond of bonds) {
      output.push(rjust("(", level * branchIndent + cfm.BOND_CODE_WIDTH));
      this._render(output, bond, level);
      output.push(rjust(")", level * branchIndent + cfm.BOND_CODE_WIDTH));
    }
  }

  // recursively render the molecule.
  _render(output, bond, level) {
    output.push(bond.render(level));
    const branches = bond.descendants;

    if (bond === this.exitBond) {
      // wrap all downstream bonds in branch
      this._renderBranches(output, level + 1, branches);
    } else if (branches.length) {
      // prioritize bonds on the trunk from entry to exit
      let first;
      let foundTrunk = false;
      for (let i = 0; i < branches.length; i++) {
        if (branches[i].isTrunk) {
          [first] = branches.splice(i, 1);
          foundTrunk = true;
          break;
        }
      }
      if (!foundTrunk) {
        [first] = branches.splice(0, 1);
      }

      this._renderBranches(output, level + 1, branches);
      this._render(output, first, level);
    }
  }

  // this calculates the approximate width and height of the rendered
  // molecule, in units of chemfig standard bond length (multiply with
  // chemfig \setatomsep parameter to obtain the physical size).
  dimensions() {
    let minX = null;
    let maxX = null;
    let minY = null;
    let maxY = null;

    const alpha = (this.options.rotate * Math.PI) / 180;
    const sinAlpha = Math.sin(alpha);
    const cosAlpha = Math.cos(alpha);

    for (const atom of this.atoms) {
      const { x, y } = atom;
      const xt = x * cosAlpha - y * sinAlpha;
      const yt = x * sinAlpha + y * cosAlpha;

      if (minX === null || xt < minX) minX = xt;
      if (maxX === null || xt > maxX) maxX = xt;
      if (minY === null || yt < minY) minY = yt;
      if (maxY === null || yt > maxY) maxY = yt;
    }

    const xSize = (maxX - minX) * this.bondScale;
    const ySize = (maxY - minY) * this.bondScale;

    return [xSize, ySize];
  }
}

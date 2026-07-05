// port of mol2chemfigPy3/atom.py

import * as cfm from "./chemfigMappings.js";
import { pyMod } from "./common.js";

// some atoms should carry their hydrogen to the left, rather than
// to the right. This is applied to solitary atoms, but not to bonded
// functional groups that contain those elements.
export const hydrogenLefties = new Set(["O", "S", "Se", "Te", "F", "Cl", "Br", "I", "At"]);

const EXPLICIT_CHARACTERS = new Set([..."ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"]);

function tupleSort(aux) {
  // aux: array of [score, priority, name]; mirrors Python's tuple sort
  // (ascending, compared element by element).
  aux.sort((a, b) => {
    if (a[0] !== b[0]) return a[0] - b[0];
    if (a[1] !== b[1]) return a[1] - b[1];
    if (a[2] < b[2]) return -1;
    if (a[2] > b[2]) return 1;
    return 0;
  });
  return aux;
}

export class Atom {
  static quadrantTurf = 80; // 80 degrees have to remain free on either side

  static quadrants = [
    // quadrants for hydrogen placement
    [0, 0, "east"],
    [1, 180, "west"],
    [2, 270, "south"],
    [3, 90, "north"],
  ];

  static chargePositions = [
    // angles for placement of detached charges
    [0, 15, "top_right"],
    [1, 165, "top_left"],
    [2, 90, "top_center"],
    [3, 270, "bottom_center"],
    [4, 345, "bottom_right"],
    [5, 195, "bottom_left"],
  ];

  static chargeTurf = 50; // reserved angle for charges - needs to be big enough for 2+

  constructor(options, idx, x, y, element, hydrogens, charge, radical, neighbors) {
    this.options = options;
    this.idx = idx;
    this.x = x;
    this.y = y;
    this.element = element;
    this.hydrogens = hydrogens;
    this.charge = charge;
    this.radical = radical;
    this.neighbors = neighbors; // the indexes only
    this.firstQuadrant = null;
    this.secondQuadrant = null;
    this.stringPos = null;
    this.phantom = null;
    this.phantomPos = null;
    this.chargeAngle = null;
    // angles of all attached bonds - to be populated later
    this.bondAngles = [];
    this.explicit = false; // flag for explicitly printed atoms - set later

    const marker = this.options.markers ?? null;
    this.marker = marker !== null ? `${marker}${this.idx + 1}` : "";
  }

  static _scoreAngle(a, b, turf) {
    const diff = pyMod(a - b, 360);
    const angle = Math.min(diff, 360 - diff);
    return Math.max(0, turf - angle) ** 2;
  }

  _scoreAngles(choices, turf) {
    const aux = [];
    for (const [priority, choiceAngle, name] of choices) {
      let score = 0;
      for (const bondAngle of this.bondAngles) {
        score += Atom._scoreAngle(choiceAngle, bondAngle, turf);
      }
      aux.push([score, priority, name]);
    }
    tupleSort(aux);
    return aux.map((a) => a[a.length - 1]);
  }

  scoreAngles() {
    if (this.bondAngles.length > 0) {
      // this atom is bonded
      const quadrants = this._scoreAngles(Atom.quadrants, Atom.quadrantTurf);
      this.firstQuadrant = quadrants[0];
      this.secondQuadrant = quadrants[1]; // 2nd choice may be used for radical electrons
    } else {
      // this atom is solitary
      if (hydrogenLefties.has(this.element)) {
        this.firstQuadrant = "west";
        this.secondQuadrant = "east";
      } else {
        this.firstQuadrant = "east";
        this.secondQuadrant = "west";
      }
    }

    this.chargeAngle = this._scoreAngles(Atom.chargePositions, Atom.chargeTurf)[0];
  }

  // render a bond that closes a ring or loop, or for late-rendered cross
  // bonds. The target atom is represented by a phantom. This relies on
  // .render() having been called earlier, which it will be - atoms always
  // precede their phantoms during molecule tree traversal.
  renderPhantom() {
    const atomCode = this.phantom;
    const commentCode = cfm.formatClosureComment(this.options, this.idx + 1);
    return [atomCode, commentCode];
  }

  render() {
    const [atomCode, stringPos, phantom, phantomPos] = cfm.formatAtom(
      this.options,
      this.idx + 1,
      this.element,
      this.hydrogens,
      this.charge,
      this.radical,
      this.firstQuadrant,
      this.secondQuadrant,
      this.chargeAngle,
    );
    this.stringPos = stringPos;
    this.phantom = phantom;
    this.phantomPos = phantomPos;

    let commentCode = cfm.formatAtomComment(this.options, this.idx + 1);
    const markerCode = cfm.formatMarker(this.marker);
    if (markerCode) {
      commentCode = " "; // force an empty comment, needed after markers
    }

    this.explicit = [...atomCode].some((ch) => EXPLICIT_CHARACTERS.has(ch));
    return [markerCode + atomCode, commentCode];
  }
}

// port of mol2chemfigPy3/chemfig_mappings.py
//
// definitions and code to translate the molecule tree to chemfig.
// this code will only make sense to you if you are familiar with the
// TeX syntax defined by the chemfig package.

import { pyRound, pyMod, pyFormat, dedent } from "./common.js";

export const BOND_CODE_WIDTH = 50; // space for bonds - generous upfront, trimmed at the end
export const TERSE_LINE_WIDTH = 75; // in terse code format, force linebreaks

export function numRound(num, sig) {
  return pyRound(num, sig);
}

export const bondCodes = {
  // bond_type -> chemfig bond code. defaults to '-'
  double: "=",
  triple: "~",
  upto: "<",
  downto: "<:",
  upfrom: ">",
  downfrom: ">:",
};

export const bondTypeTikz = { link: "draw=none", either: "mcfwavy" }; // bond type -> tikz

export const bondStyles = {
  // bond style -> tikz template
  cross: "mcfx={%(bgstart)s}{%(bgend)s}",
  double_left: "dbl={%(start)s}{%(end)s}",
  double_right: "dbr={%(start)s}{%(end)s}",
  triple: "trpl={%(start)s}{%(end)s}",
  // combined styles for double, triple and cross
  cross_double_left: "dblx={%(start)s}{%(end)s}{%(bgstart)s}{%(bgend)s}",
  cross_double_right: "dbrx={%(start)s}{%(end)s}{%(bgstart)s}{%(bgend)s}",
  cross_triple: "trplx={%(start)s}{%(end)s}{%(bgstart)s}{%(bgend)s}",
};

export const bondStyleShortcuts = {
  // style shortcuts for double bonds in hexagons etc
  "dbr={58}{58}": "drh",
  "dbl={58}{58}": "dlh",
  "dbr={0}{58}": "drhe",
  "dbl={0}{58}": "dlhe",
  "dbr={58}{0}": "drhs",
  "dbl={58}{0}": "dlhs",
  "dbr={0}{0}": "drn",
  "dbl={0}{0}": "dln",
};

export const macroTemplates = {
  // various custom LaTeX macros
  plus_charge: "\\mcfplus",
  minus_charge: "\\mcfminus",
  phantom: "\\phantom{%s}", // phantom at end of ring-closing bonds
  aromatic_circle: "\\mcfcringle{%s}", // circle inside an aromatic ring
  aromatic_circle_bond: "-[%(angle)s,%(length)s,,,draw=none]", // bond connecting circle to atom
  cross_blank: "draw=none",
  cross_draw: "mcfcrossbond",
  marker: "@{%s}", // markers identifying atoms and bonds
};

export const radicalTemplates = {
  east: "\\lewis{0%s,%s}",
  north: "\\lewis{2%s,%s}",
  west: "\\lewis{4%s,%s}",
  south: "\\lewis{6%s,%s}",
};

export const radicalTemplates2 = {
  // for ChemFig version >= 1.6
  east: "\\charge{0=\\%s}{%s}",
  north: "\\charge{90=\\%s}{%s}",
  west: "\\charge{180=\\%s}{%s}",
  south: "\\charge{270=\\%s}{%s}",
};

export const atomTemplates = {
  // templates for atoms, specialized for different numbers and preferred
  // quadrants of attached hydrogen and charges. each leaf is [template, string_pos]
  atom_no: {
    empty: ["\\mcfatomno{%(number)s}", 0],
    east: ["\\mcfright{%(element)s}{\\mcfatomno{%(number)s}}", 0],
    west: ["\\mcfleft{\\mcfatomno{%(number)s}}{%(element)s}", 0],
    north: ["\\mcfabove{%(element)s}{\\mcfatomno{%(number)s}}", 0],
    south: ["\\mcfbelow{%(element)s}{\\mcfatomno{%(number)s}}", 0],
  },
  neutral: {
    one_h: {
      east: ["%(element)sH", 1],
      west: ["H%(element)s", 2],
      north: ["\\mcfabove{%(element)s}{H}", 0],
      south: ["\\mcfbelow{%(element)s}{H}", 0],
    },
    more_h: {
      east: ["%(element)sH_%(hydrogens)s", 1],
      west: ["H_%(hydrogens)s%(element)s", 2],
      north: ["\\mcfabove{%(element)s}{\\mcfright{H}{_%(hydrogens)s}}", 0],
      south: ["\\mcfbelow{%(element)s}{\\mcfright{H}{_%(hydrogens)s}}", 0],
    },
  },
  charged: {
    no_h: {
      top_right: ["\\mcfright{%(element)s}{^{%(charge)s}}", 0],
      top_left: ["^{%(charge)s}%(element)s", 2],
      top_center: ["\\mcfabove{%(element)s}{_{%(charge)s}}", 0],
      bottom_right: ["\\mcfright{%(element)s}{_{%(charge)s}}", 0],
      bottom_left: ["_{%(charge)s}%(element)s", 2],
      bottom_center: ["\\mcfbelow{%(element)s}{^{%(charge)s}}", 0],
    },
    one_h: {
      east: ["%(element)sH^{%(charge)s}", 1],
      west: ["^{%(charge)s}H%(element)s", 3],
      north: ["\\mcfaboveright{%(element)s}{H}{^{%(charge)s}}", 0],
      south: ["\\mcfbelowright{%(element)s}{H}{^{%(charge)s}}", 0],
    },
    more_h: {
      east: ["%(element)sH_%(hydrogens)s^{%(charge)s}", 1],
      west: ["^{%(charge)s}H_%(hydrogens)s%(element)s", 3],
      north: ["\\mcfaboveright{%(element)s}{H}{^{%(charge)s}_%(hydrogens)s}", 0],
      south: ["\\mcfbelowright{%(element)s}{H}{^{%(charge)s}_%(hydrogens)s}", 0],
    },
  },
};

// helpers for bond formatting

export function formatAngle(options, angle, parentAngle) {
  let prefix;
  if (options.relative_angles && parentAngle !== null && parentAngle !== undefined) {
    angle -= parentAngle;
    prefix = "::";
  } else {
    prefix = ":";
  }

  angle = numRound(angle, options.angle_round);

  return prefix + String(pyMod(angle, 360));
}

export function specifierDefault(val, defaultVal) {
  if (val === defaultVal) return "";
  return String(val);
}

// the master bond formatter

export function formatBond(
  options,
  angle,
  parentAngle,
  bondType,
  clockwise,
  isLast,
  length,
  departure,
  arrival,
  tikzStyles,
  tikzValues,
  marker,
) {
  if (angle === null || angle === undefined) {
    // angle is None -- first atom only.
    return "";
  }

  angle = formatAngle(options, angle, parentAngle);
  angle = specifierDefault(angle, ":0");

  length = numRound(length, options.bond_round);
  length = specifierDefault(length, 1);

  departure = specifierDefault(departure, 0);
  arrival = specifierDefault(arrival, 0);

  const bondCode = bondCodes[bondType] ?? "-";

  const tikzFilled = [];

  const btt = bondTypeTikz[bondType];
  if (btt !== undefined) {
    tikzFilled.push(btt);
  }

  if (tikzStyles && tikzStyles.size) {
    const key = [...tikzStyles].sort().join("_");

    const tikz = pyFormat(bondStyles[key], tikzValues);
    tikzFilled.push(tikz);

    if (key.includes("cross") && !isLast) {
      // departure atom is empty or a phantom, so at most 1 character.
      // is_last guards against edge case.
      departure = "";
    }
  }

  let tikz = tikzFilled.join(",");
  tikz = bondStyleShortcuts[tikz] ?? tikz; // replace tikz with shortcut if available

  let specifiers = [angle, length, departure, arrival, tikz].join(",").replace(/,+$/, "");

  if (marker) {
    specifiers = formatMarker(marker) + specifiers;
  }

  if (specifiers) {
    specifiers = `[${specifiers}]`;
  }

  // modify double bonds in non-aromatic rings
  let modifier = "";
  if (bondType === "double" && clockwise !== 0) {
    modifier = clockwise === 1 ? "_" : "^";
  }

  return bondCode + modifier + specifiers;
}

export function fillAtom(keys, data, phantom, phantomPos = 0) {
  let thing = atomTemplates[keys[0]];

  for (const key of keys.slice(1)) {
    thing = thing[key];
  }

  const [template, stringPos] = thing;
  return [pyFormat(template, data), stringPos, phantom, phantomPos];
}

export function formatMarker(marker) {
  if (marker) {
    marker = pyFormat(macroTemplates.marker, marker);
  }
  return marker;
}

export function formatAtom(
  options,
  idx,
  element,
  hydrogens,
  charge,
  radical,
  firstQuadrant,
  secondQuadrant,
  chargeAngle,
) {
  const mt = macroTemplates;
  const activeRadicalTemplates = options.legacy_lewis ? radicalTemplates : radicalTemplates2;

  let radicalElement;
  if (radical === 0) {
    radicalElement = element;
  } else {
    const radicalSymbol = radical === 1 ? "." : ":";
    const radicalQuadrant = hydrogens ? secondQuadrant : firstQuadrant;
    radicalElement = pyFormat(activeRadicalTemplates[radicalQuadrant], [radicalSymbol, element]);
  }

  const data = { number: idx, hydrogens, element: radicalElement };

  // we almost always need the same phantom string, so we prepare it once
  const elementPhantom = pyFormat(mt.phantom, data.element);

  // deal with atom numbers first
  if (options.atom_numbers) {
    if (element === "C" && !options.show_carbons) {
      const phantom = pyFormat(mt.phantom, idx);
      return fillAtom(["atom_no", "empty"], data, phantom);
    }

    // not an empty carbon
    return fillAtom(["atom_no", firstQuadrant], data, elementPhantom);
  }

  // full atoms, no numbers

  // neutrals
  if (charge === 0) {
    // empty carbons. This case is so simple we don't use a template.
    if (data.element === "C" && !options.show_carbons && (!options.show_methyls || hydrogens < 3)) {
      return ["", 0, "", 0];
    }

    // next simplest case: neutral atom without hydrogen
    if (!hydrogens) {
      return [data.element, 0, elementPhantom, 0];
    }

    // one or more hydrogen
    const keys = hydrogens === 1 ? ["neutral", "one_h", firstQuadrant] : ["neutral", "more_h", firstQuadrant];
    return fillAtom(keys, data, elementPhantom);
  }

  // at this point, we have a charged atom

  // format dict entry for charge, as it is configurable
  if (charge > 0) {
    data.charge = mt.plus_charge;
  } else {
    data.charge = mt.minus_charge;
  }

  if (Math.abs(charge) > 1) {
    data.charge = String(Math.abs(charge)) + data.charge;
  }

  let keys;
  if (!hydrogens) {
    keys = ["charged", "no_h", chargeAngle];
  } else if (hydrogens === 1) {
    keys = ["charged", "one_h", firstQuadrant];
  } else {
    keys = ["charged", "more_h", firstQuadrant];
  }

  return fillAtom(keys, data, elementPhantom);
}

export function formatAtomComment(options, idx) {
  if (options.terse) return "";
  return String(idx);
}

export function formatClosureComment(options, idx) {
  if (options.terse) return "";
  return `-> ${idx}`;
}

export function formatAromaticRing(options, angle, parentAngle, length, radius) {
  const values = {
    angle: formatAngle(options, angle, parentAngle),
    length: specifierDefault(length, 1),
  };

  const ringBondCode = pyFormat(macroTemplates.aromatic_circle_bond, values);
  const ringCode = pyFormat(macroTemplates.aromatic_circle, radius);

  const comment = options.terse ? "" : "(o)";

  return [ringBondCode, ringCode, comment];
}

export function stripOutput(outputList) {
  const stripped = outputList.map((line) => line.split("%")[0].trim());
  stripped.reverse();

  const chunked = [];
  let acc = "";

  while (stripped.length) {
    const popped = stripped.pop();
    if (acc.length + popped.length > TERSE_LINE_WIDTH) {
      chunked.push(acc);
      acc = popped;
    } else {
      acc += popped;
    }
  }
  if (acc) {
    chunked.push(acc);
  }

  return chunked;
}

export function formatOutput(options, outputList) {
  // first, do a bit of prettification by removing excessive indentation
  const indentStr = " ".repeat(options.indent);

  const joined = dedent(outputList.join("\n")).split("\n");
  let result = joined.map((line) => indentStr + line);

  if (options.submol_name !== null && options.submol_name !== undefined) {
    result = [`\\definesubmol{${options.submol_name}}{`, ...result, "}"];
  } else if (options.chemfig_command) {
    result = ["\\chemfig{", ...result, "}"];
  }

  let joiner;
  if (options.terse) {
    result = stripOutput(result);
    joiner = "%\n";
  } else {
    joiner = "\n";
  }

  return result.join(joiner);
}

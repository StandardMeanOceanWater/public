// port of mol2chemfigPy3/common.py

export const programVersion = "1.6.0";

// settings dict contains fixed settings that are not exposed as options.
// a copy of this object is merged with option defaults (see options.js)
// and passed around during processing.
export const settings = {
  input_mode: "auto",
  relative_angles: false,
  bond_round: 3,
  angle_round: 1,
  quadrant_tolerance: 0.1,
};

export class MCFError extends Error {
  constructor(text) {
    super(String(text));
    this.name = "MCFError";
    this.text = String(text);
  }

  toString() {
    return this.text;
  }
}

// a simple Counter class mirroring common.py's Counter
export class Counter {
  constructor(lst) {
    this._d = new Map();
    for (const val of lst) {
      if (!this._d.has(val)) {
        this._d.set(val, 0);
      }
      this._d.set(val, this._d.get(val) + 1);
    }
  }

  mostCommon() {
    const lst = [...this._d.entries()];
    lst.sort((a, b) => a[1] - b[1]);
    return lst[lst.length - 1][0];
  }
}

// Decompose a non-negative finite double into its *exact* decimal digits
// (intPart, fracPart), via the IEEE754 bit pattern. Needed because pyRound
// must replicate CPython's round(), which is correctly-rounded against the
// true binary value of the float -- not against its naive decimal look.
function floatToExactDecimalParts(ax) {
  const buf = new ArrayBuffer(8);
  new Float64Array(buf)[0] = ax;
  const bits = new BigUint64Array(buf)[0];
  const rawExp = Number((bits >> 52n) & 0x7ffn);
  const rawMant = bits & 0xfffffffffffffn;

  let e, m;
  if (rawExp === 0) {
    e = -1074; // subnormal
    m = rawMant;
  } else {
    e = rawExp - 1075;
    m = rawMant | 0x10000000000000n;
  }

  if (m === 0n) return ["0", ""];

  if (e >= 0) {
    return [(m << BigInt(e)).toString(), ""];
  }

  const shift = -e;
  let digits = (m * 5n ** BigInt(shift)).toString();
  if (digits.length <= shift) {
    digits = "0".repeat(shift - digits.length + 1) + digits;
  }
  const intPart = digits.slice(0, digits.length - shift);
  const fracPart = digits.slice(digits.length - shift);
  return [intPart, fracPart];
}

// mirrors Python 3's round(x, ndigits) for ndigits >= 0: correctly-rounded
// round-half-to-even against the exact binary value of x (not a naive
// multiply/round/divide, which would re-introduce float error Python doesn't
// have). This codebase never rounds with ndigits < 0.
export function pyRound(x, ndigits = 0) {
  if (!Number.isFinite(x) || x === 0) return x === 0 ? 0 : x;

  const neg = x < 0;
  const ax = Math.abs(x);
  let [intPart, fracPart] = floatToExactDecimalParts(ax);

  if (fracPart.length < ndigits) {
    fracPart += "0".repeat(ndigits - fracPart.length);
  }

  const keep = ndigits > 0 ? fracPart.slice(0, ndigits) : "";
  const rest = fracPart.slice(ndigits);

  let roundUp = false;
  if (rest.length > 0) {
    const firstDropped = rest[0];
    if (firstDropped > "5") {
      roundUp = true;
    } else if (firstDropped === "5") {
      if (/[1-9]/.test(rest.slice(1))) {
        roundUp = true;
      } else {
        const lastKept = keep.length > 0 ? keep[keep.length - 1] : intPart[intPart.length - 1];
        roundUp = Number(lastKept) % 2 === 1;
      }
    }
  }

  let combined = BigInt((intPart + keep) || "0");
  if (roundUp) combined += 1n;
  let combinedStr = combined.toString();

  let result;
  if (ndigits > 0) {
    if (combinedStr.length <= ndigits) {
      combinedStr = "0".repeat(ndigits - combinedStr.length + 1) + combinedStr;
    }
    const ip = combinedStr.slice(0, combinedStr.length - ndigits);
    const fp = combinedStr.slice(combinedStr.length - ndigits);
    result = Number(ip + "." + fp);
  } else {
    result = Number(combinedStr);
  }

  return neg ? -result : result;
}

// mirrors Python's `%` (floor-mod: result always has the sign of b).
// JS's `%` is a remainder op (sign follows a), so e.g. -30 % 360 gives -30
// in JS but 330 in Python -- every angle-wrapping mod in this codebase
// needs this instead of the raw operator.
//
// NB: this must add `b` at most *once*, only when the raw remainder came
// back negative -- unconditionally doing `((a % b) + b) % b` looks
// equivalent but silently reintroduces float noise even when a is already
// in [0, b) (e.g. 29.9 % 360 is exactly 29.9, but (29.9 + 360) % 360
// computes 389.9 % 360, which is not exactly representable and comes back
// as 29.899999999999977). Python's float % doesn't have this problem
// because it's a single correctly-rounded fmod, not a double round trip.
export function pyMod(a, b) {
  const r = a % b;
  return r < 0 ? r + b : r;
}

// mirrors Python's str.rjust(width): left-pad with spaces, never truncates.
export function rjust(s, width) {
  return s.length >= width ? s : " ".repeat(width - s.length) + s;
}

// mirrors Python's `template % data`:
// - data a plain object -> replaces %(key)s tokens (chemfig_mappings' dict templates)
// - data anything else -> treated as a single value or an array of positional
//   values substituted into %s tokens in order (radical_templates etc.)
export function pyFormat(template, data) {
  if (data !== null && typeof data === "object" && !Array.isArray(data)) {
    return template.replace(/%\((\w+)\)s/g, (_, key) => String(data[key]));
  }
  const args = Array.isArray(data) ? data : [data];
  let i = 0;
  return template.replace(/%s/g, () => String(args[i++]));
}

// mirrors Python's textwrap.dedent: strips the longest common leading
// whitespace shared by all non-blank lines; whitespace-only lines are
// normalized to empty and don't count toward the margin.
export function dedent(text) {
  const wsOnlyLine = /^[ \t]+$/;
  const lines = text.split("\n").map((line) => (wsOnlyLine.test(line) ? "" : line));

  const indents = [];
  for (const line of lines) {
    if (line === "") continue;
    indents.push(/^[ \t]*/.exec(line)[0]);
  }

  let margin = null;
  for (const indent of indents) {
    if (margin === null) {
      margin = indent;
    } else if (indent.startsWith(margin)) {
      // current margin already common, keep it
    } else if (margin.startsWith(indent)) {
      margin = indent;
    } else {
      margin = "";
      break;
    }
  }

  if (margin) {
    return lines.map((line) => (line.startsWith(margin) ? line.slice(margin.length) : line)).join("\n");
  }
  return lines.join("\n");
}

// Engine adapter: turns a pair of RDKit.js-produced V2000 molblocks into
// the small Indigo-shaped interface molecule.js expects from `tkmol`.
//
// Per the porting blueprint, the intended pipeline is:
//   RDKit.get_mol(smiles) -> mol.set_new_coords(true) (CoordGen)
//   -> mol.get_molblock() + mol.get_aromatic_form() -> (this module)
//   -> Molecule(options, tkmol)
//
// molecule.js only ever calls four things on `tkmol`: iterateAtoms(),
// iterateBonds(), aromatize(), iterateSSSR() -- everything else Indigo
// offers (unfoldHydrogens, layout, hasCoord, ...) is handled up front in
// index.js against RDKit's real API, not simulated here.
//
// Two molblocks, not one: get_molblock() always Kekulizes (bond orders
// 1/2/3, never MDL's aromatic 4), which is what we need for the atom/bond
// graph and for parseBonds()'s initial (pre-aromatize) bond_type -- that
// matches Indigo's behavior too, since parseBonds() runs before
// annotateRings() ever calls aromatize(). But annotateRings() itself
// needs real aromaticity perception, which get_aromatic_form() provides
// (same atom/bond order, just bond order 4 on aromatic ring bonds).
// aromatize() below cross-references the two by bond position and flips
// the Kekulized bonds' *reported* order to 4 -- mutating the adapter's
// data, not any already-built Bond object, exactly mirroring how
// Indigo's tkmol.aromatize() only affects toolkit-bond queries made
// after it's called.

import { findSSSR } from "./sssr.js";

// standard (neutral, lowest) valences used to derive implicit hydrogen
// counts from the Kekulized bond graph -- the same role Indigo's
// countImplicitHydrogens() / RDKit's sanitization play internally. Formal
// charge shifts the natural valence the way it shifts the octet (NH4+
// behaves like carbon); radical electrons occupy bonding slots too.
const STANDARD_VALENCES = {
  H: [1],
  B: [3],
  C: [4],
  N: [3, 5],
  O: [2],
  F: [1],
  Si: [4],
  P: [3, 5],
  S: [2, 4, 6],
  Cl: [1, 3, 5, 7],
  Br: [1],
  I: [1, 3, 5, 7],
};

function computeImplicitHydrogens(element, explicitValenceSum, charge, radicalElectrons) {
  const valences = STANDARD_VALENCES[element];
  if (!valences) return 0; // metals and other non-organic-subset atoms: no implicit H

  const adjusted = explicitValenceSum + radicalElectrons - charge;
  for (const v of valences) {
    if (v >= adjusted) return Math.max(0, v - adjusted);
  }
  return 0; // hypervalent beyond all standard valences: no implicit H
}

// MDL inline atom-charge column codes (legacy field; modern writers
// usually leave this 0 and use the M CHG property block instead, which
// parseMolblockV2000 prefers when present).
const INLINE_CHARGE_CODES = { 0: 0, 1: 3, 2: 2, 3: 1, 4: 0, 5: -1, 6: -2, 7: -3 };

// MDL M RAD property codes (spin multiplicity) -> unpaired-electron count
// as mol2chemfigPy3's Atom expects it (only used to pick "." vs ":" in
// chemfig_mappings' radical templates, so singlet/triplet both mean "2").
const RAD_CODE_TO_ELECTRONS = { 1: 2, 2: 1, 3: 2 };

export function parseMolblockV2000(text) {
  const lines = text.split(/\r\n|\r|\n/);

  const countsLine = lines[3] ?? "";
  const numAtoms = parseInt(countsLine.slice(0, 3), 10) || 0;
  const numBonds = parseInt(countsLine.slice(3, 6), 10) || 0;

  const atoms = [];
  for (let i = 0; i < numAtoms; i++) {
    const line = lines[4 + i] ?? "";
    const x = parseFloat(line.slice(0, 10));
    const y = parseFloat(line.slice(10, 20));
    const element = line.slice(31, 34).trim();
    const inlineChargeCode = parseInt(line.slice(36, 39), 10) || 0;

    atoms.push({
      element,
      x,
      y,
      charge: INLINE_CHARGE_CODES[inlineChargeCode] ?? 0,
      radical: inlineChargeCode === 4 ? 1 : 0,
      neighbors: [],
      explicitValenceSum: 0,
    });
  }

  const bondsStart = 4 + numAtoms;
  const bonds = [];
  for (let i = 0; i < numBonds; i++) {
    const line = lines[bondsStart + i] ?? "";
    const a1 = parseInt(line.slice(0, 3), 10) - 1;
    const a2 = parseInt(line.slice(3, 6), 10) - 1;
    const order = parseInt(line.slice(6, 9), 10) || 1;
    const stereo = parseInt(line.slice(9, 12), 10) || 0;

    bonds.push({ start: a1, end: a2, order, stereo });

    atoms[a1].neighbors.push(a2);
    atoms[a2].neighbors.push(a1);
    // Kekulized order (1/2/3) sums directly into valence; an aromatic (4)
    // bond -- not expected from RDKit's writer, see module docstring --
    // would need its ring's alternating pattern resolved first, so we
    // just count it as a single bond rather than mis-valence the atom.
    const valenceContribution = order === 4 ? 1 : order;
    atoms[a1].explicitValenceSum += valenceContribution;
    atoms[a2].explicitValenceSum += valenceContribution;
  }

  // property block: M  CHG / M  RAD override the legacy inline codes
  for (let i = bondsStart + numBonds; i < lines.length; i++) {
    const line = lines[i];
    if (line == null) continue;
    if (line.startsWith("M  END")) break;

    if (line.startsWith("M  CHG") || line.startsWith("M  RAD")) {
      const tokens = line.trim().split(/\s+/);
      const kind = tokens[1]; // CHG or RAD
      const count = parseInt(tokens[2], 10) || 0;
      for (let p = 0; p < count; p++) {
        const atomIdx = parseInt(tokens[3 + p * 2], 10) - 1;
        const value = parseInt(tokens[4 + p * 2], 10);
        if (!atoms[atomIdx]) continue;
        if (kind === "CHG") {
          atoms[atomIdx].charge = value;
          atoms[atomIdx].radical = 0; // M CHG entries are never also radicals
        } else {
          atoms[atomIdx].radical = RAD_CODE_TO_ELECTRONS[value] ?? 0;
        }
      }
    }
  }

  for (const atom of atoms) {
    atom.hydrogens = computeImplicitHydrogens(
      atom.element,
      atom.explicitValenceSum,
      atom.charge,
      atom.radical,
    );
  }

  return { atoms, bonds };
}

// wraps parsed molblock data into the Indigo-shaped interface
// molecule.js's Molecule constructor expects as `tkmol`.
//
// @param molblockText          Kekulized V2000 molblock (mol.get_molblock())
// @param aromaticMolblockText  same molecule's aromatic-form molblock
//                              (mol.get_aromatic_form()) -- optional; without
//                              it, aromatize() has nothing to flip and every
//                              ring renders with alternating Kekulized double
//                              bonds instead of a circle (equivalent to the
//                              default aromatic_circles=false rendering).
// Clear isAromaticRingBond on bonds that Indigo would treat as
// non-aromatic: those living only in rings that contain an atom bearing an
// exocyclic double bond (e.g. a ring carbonyl). A bond survives as aromatic
// if it belongs to at least one ring free of such atoms -- so a fusion bond
// shared with a genuinely aromatic ring keeps its aromatic flag. Mutates
// `bonds` in place. See adaptMolblock for why this matters.
function deAromatizeExocyclicRings(numAtoms, bonds) {
  const rings = findSSSR(
    numAtoms,
    bonds.map((b) => ({ start: b.start, end: b.end })),
  );
  if (rings.length === 0) return;

  const ringBondIdxSet = new Set();
  for (const ring of rings) for (const bi of ring.bondIdxs) ringBondIdxSet.add(bi);

  // an atom has an exocyclic double bond if it sits on a Kekulized double
  // bond that is not itself part of any ring (a ring C=O, C=N-oxide, etc.).
  const hasExocyclicDouble = new Array(numAtoms).fill(false);
  bonds.forEach((bond, i) => {
    if (bond.order === 2 && !ringBondIdxSet.has(i)) {
      hasExocyclicDouble[bond.start] = true;
      hasExocyclicDouble[bond.end] = true;
    }
  });

  // union of bonds belonging to at least one "clean" ring (no exocyclic
  // double-bond atom). These keep their aromatic flag; everything else loses it.
  const cleanAromaticBonds = new Set();
  for (const ring of rings) {
    const clean = ring.atoms.every((a) => !hasExocyclicDouble[a]);
    if (clean) for (const bi of ring.bondIdxs) cleanAromaticBonds.add(bi);
  }

  bonds.forEach((bond, i) => {
    if (bond.isAromaticRingBond && !cleanAromaticBonds.has(i)) {
      bond.isAromaticRingBond = false;
    }
  });
}

export function adaptMolblock(molblockText, aromaticMolblockText = null) {
  const { atoms, bonds } = parseMolblockV2000(molblockText);

  if (aromaticMolblockText) {
    const aromaticForm = parseMolblockV2000(aromaticMolblockText);
    bonds.forEach((bond, i) => {
      bond.isAromaticRingBond = aromaticForm.bonds[i]?.order === 4;
    });

    // Reconcile RDKit's aromaticity model with Indigo's, which the
    // mol2chemfigPy3 oracle uses. RDKit aromatizes rings whose atoms carry
    // exocyclic double bonds (the urea/amide carbonyl rings of caffeine,
    // xanthine, guanine and the other nucleobases); Indigo does not. That
    // disagreement doesn't change which bonds render as double -- those come
    // from the Kekulized graph either way -- but annotateRings() sorts rings
    // by aromaticity, and the sort order decides which ring claims a shared
    // fusion bond first when assigning its (assign-once) clockwise flag. A
    // ring wrongly flagged aromatic reorders that and flips the inner
    // double-bond stroke's side (=_ vs =^). We match Indigo by de-aromatizing
    // any bond that only belongs to rings containing an exocyclic-double-bond
    // atom (bonds shared with a genuinely aromatic ring stay aromatic).
    deAromatizeExocyclicRings(atoms.length, bonds);
  }

  const atomWrappers = atoms.map((atom, idx) => {
    const wrapper = {
      index: () => idx,
      symbol: () => atom.element,
      countImplicitHydrogens: () => atom.hydrogens,
      charge: () => atom.charge,
      radicalElectrons: () => atom.radical,
      xyz: () => [atom.x, atom.y, 0],
      iterateNeighbors: () => atom.neighbors.map((n) => atomWrappers[n]),
    };
    return wrapper;
  });

  const bondWrappers = bonds.map((bond) => ({
    source: () => atomWrappers[bond.start],
    destination: () => atomWrappers[bond.end],
    bondOrder: () => bond.order,
    bondStereo: () => bond.stereo,
  }));

  return {
    iterateAtoms: () => atomWrappers.slice(),
    iterateBonds: () => bondWrappers.slice(),

    // flips aromatic-ring bonds' *reported* order to 4, in place -- only
    // affects bondOrder() calls made after this runs (see module docstring).
    aromatize: () => {
      for (const bond of bonds) {
        if (bond.isAromaticRingBond) bond.order = 4;
      }
    },

    iterateSSSR: () => {
      const rings = findSSSR(
        atoms.length,
        bonds.map((b) => ({ start: b.start, end: b.end })),
      );
      return rings.map((ring) => {
        const ringBondWrappers = ring.bondIdxs.map((bondIdx) => bondWrappers[bondIdx]);
        return { iterateBonds: () => ringBondWrappers };
      });
    },
  };
}

// mol2chemfig-js — a JavaScript port of mol2chemfigPy3.
//
// Derived from mol2chemfigPy3 (© 2021 Nianze Tao, MIT License), itself a
// py2→py3 translation of the original mol2chemfig v1.5 (E. K. Brefo-Mensah &
// M. Palmer, University of Waterloo). This port is distributed under MIT;
// upstream copyright notices and full license texts are in
// ../THIRD-PARTY-NOTICES.md. SPDX-License-Identifier: MIT
//
// port of mol2chemfigPy3/processor.py's parseMolecule() + process(), against
// RDKit.js instead of Indigo.
//
// This module doesn't load or initialize RDKit.js itself -- the caller
// passes in an already-initialized RDKit module object (the result of
// `await initRDKitModule()`), so this code works the same whether RDKit
// was loaded via a <script> tag in the browser (ChemLatex.html) or via
// require()/import in Node (the golden-set comparison script, task
// "用 MOL_LIST.csv 跑金標準比對").
//
// Pipeline (see the porting blueprint, section 3, and molblockAdapter.js):
//   RDKit.get_mol(smiles) -> [add_hs_in_place/remove_hs_in_place per
//   options.hydrogens] -> set_new_coords(true) (CoordGen)
//   -> get_molblock() + get_aromatic_form() -> adaptMolblock()
//   -> new Molecule(options, tkmol)

import { MCFError } from "./common.js";
import { getDefaultOptions } from "./options.js";
import { adaptMolblock } from "./molblockAdapter.js";
import { Molecule } from "./molecule.js";

// Bump when the port's rendering algorithm changes, so generated chemfig is
// traceable to a code revision (mirrors ChemLatex.html's legacy
// CHEMFIG_VERSION). 2026-07-06: Indigo-aligned aromaticity + SSSR ring order.
export const PORT_VERSION = "mcf-js-2026.07.06";

// build a Molecule from a SMILES (or molfile) string. `userOptions`
// overrides individual keys in options.js's getDefaultOptions() --
// see that file for the full list (rotate, flip_horizontal, hydrogens,
// aromatic_circles, bond_scale, ...).
export function moleculeFromSmiles(RDKit, smiles, userOptions = {}) {
  const options = { ...getDefaultOptions(), ...userOptions };

  const mol = RDKit.get_mol(smiles);
  if (!mol) {
    throw new MCFError("Invalid input data");
  }

  try {
    if (options.hydrogens === "add") {
      mol.add_hs_in_place();
      // needed to give coordinates to added Hs
      mol.set_new_coords(true);
    } else if (options.hydrogens === "delete") {
      mol.remove_hs_in_place();
    }

    if (!mol.has_coords() || options.recalculate_coordinates) {
      mol.set_new_coords(true); // true = prefer CoordGen layout
    }

    const molblock = mol.get_molblock();
    const aromaticMolblock = mol.get_aromatic_form();
    const tkmol = adaptMolblock(molblock, aromaticMolblock);

    return new Molecule(options, tkmol);
  } finally {
    mol.delete(); // free the wasm-side molecule
  }
}

// convenience wrapper: SMILES straight to formatted chemfig code.
export function smilesToChemfig(RDKit, smiles, userOptions = {}) {
  const molecule = moleculeFromSmiles(RDKit, smiles, userOptions);
  return molecule.renderUser();
}

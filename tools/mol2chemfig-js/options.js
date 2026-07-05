// port of mol2chemfigPy3/options.py + optionparser.py's default-resolution logic.
//
// The Python CLI/web-form parser (optionparser.py) is not ported: this is a
// browser tool that always feeds SMILES directly, so there's no CLI argv and
// no HTML <form> fields to decode. What matters for fidelity is the *default
// value* each Option resolves to when nothing overrides it, since molecule.py
// and chemfig_mappings.py read these out of the options dict by key.
//
// Defaults below were derived option-by-option from options.py's getParser():
// BoolOption with no explicit default -> false, SelectOption with no explicit
// default -> its valid_range[0], TypeOption/RangeOption with no explicit
// default -> null. Where options.py passes an explicit default=..., that value
// is used instead (see comments).

import { settings } from "./common.js";

export function getDefaultOptions() {
  return {
    ...settings,

    help: false,
    version: false,

    // SelectOption default="file" explicit. Unused by this port: the web
    // pipeline always feeds a SMILES string directly (no CLI file/pubchem
    // input modes), so nothing reads this key.
    input: "file",

    terse: false,
    strict: true, // BoolOption default=True explicit
    indent: 4, // IntOption default=4 explicit
    recalculate_coordinates: false,
    rotate: 0.0, // FloatOption default=0.0 explicit
    relative_angles: false,
    flip_horizontal: false,
    flip_vertical: false,
    show_carbons: false,
    show_methyls: false,
    hydrogens: "keep", // SelectOption, no default -> valid_range[0]
    aromatic_circles: false,
    fancy_bonds: false,
    markers: null,
    atom_numbers: false,
    bond_scale: "normalize", // SelectOption, no default -> valid_range[0]
    bond_stretch: 1.0, // FloatOption default=1.0 explicit
    chemfig_command: false,
    submol_name: null,
    entry_atom: null,
    exit_atom: null,
    cross_bond: null,
    legacy_lewis: false,
  };
}

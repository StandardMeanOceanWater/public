// Smallest Set of Smallest Rings (ring perception).
//
// mol2chemfig needs the same "smallest set of smallest rings" that
// Indigo's iterateSSSR() gives it -- molecule.js's annotateRings()/
// aromatizeRing() walk exactly these rings to decide where double bonds
// go and how aromatic rings get drawn (see the porting blueprint, section
// 4: this is the one piece with no RDKit.js equivalent, so it's
// implemented here from scratch as pure graph theory).
//
// Ring bond/atom ORDER is not semantically meaningful to any caller in
// this codebase (annotateRing only sums/averages atom coordinates and
// bond lengths; aromatizeRing picks an arbitrary anchor bond) -- so each
// ring is returned as an unordered atom/bond-index set, not a walk.
//
// Approach ("shortest cycle per edge", a practical simplification of
// Horton's algorithm): for every bond, find the shortest path between its
// two endpoints with that bond removed; combined with the bond itself,
// that's the smallest cycle through it. Collect one candidate per bond,
// sort by size, and greedily keep candidates whose bond-set is linearly
// independent (XOR / GF(2)) of the ones already kept, stopping once we
// have (bonds - atoms + components) rings, the graph's circuit rank.
// This handles fused, bridged and spiro ring systems correctly for the
// drug-like/natural-product molecules this tool targets; pathological
// cages where the true SSSR needs vertex-based candidates too (full
// Horton's algorithm) are a known limitation -- validate against the
// mol2chemfigPy3 oracle if a specific molecule's ring set looks wrong.

function buildAdjacency(numAtoms, bonds) {
  const adjacency = Array.from({ length: numAtoms }, () => []);
  bonds.forEach((bond, bondIdx) => {
    adjacency[bond.start].push({ to: bond.end, bondIdx });
    adjacency[bond.end].push({ to: bond.start, bondIdx });
  });
  return adjacency;
}

function countComponents(numAtoms, adjacency) {
  const seen = new Array(numAtoms).fill(false);
  let components = 0;

  for (let start = 0; start < numAtoms; start++) {
    if (seen[start]) continue;
    components++;
    const stack = [start];
    seen[start] = true;
    while (stack.length) {
      const u = stack.pop();
      for (const { to } of adjacency[u]) {
        if (!seen[to]) {
          seen[to] = true;
          stack.push(to);
        }
      }
    }
  }

  return components;
}

// shortest path between `start` and `goal` with bond `excludeBondIdx`
// removed. Returns the path as a list of atom indices (both ends
// included), or null if no such path exists.
function shortestPathExcluding(numAtoms, adjacency, start, goal, excludeBondIdx) {
  const prev = new Array(numAtoms).fill(-1);
  const seen = new Array(numAtoms).fill(false);
  seen[start] = true;

  const queue = [start];
  let qi = 0;

  while (qi < queue.length) {
    const u = queue[qi++];
    if (u === goal) break;
    for (const { to, bondIdx } of adjacency[u]) {
      if (bondIdx === excludeBondIdx || seen[to]) continue;
      seen[to] = true;
      prev[to] = u;
      queue.push(to);
    }
  }

  if (!seen[goal]) return null;

  const path = [goal];
  let cur = goal;
  while (cur !== start) {
    cur = prev[cur];
    path.push(cur);
  }
  path.reverse();
  return path;
}

function xorSets(a, b) {
  const result = new Set(a);
  for (const x of b) {
    if (result.has(x)) result.delete(x);
    else result.add(x);
  }
  return result;
}

// @param numAtoms  number of atoms (nodes), indices 0..numAtoms-1
// @param bonds     array of {start, end} atom-index pairs, one per bond;
//                  the array index IS the bond's id used in the returned
//                  ring's bondIdxs.
// @returns array of rings: [{ atoms: number[], bondIdxs: number[] }, ...]
export function findSSSR(numAtoms, bonds) {
  const adjacency = buildAdjacency(numAtoms, bonds);
  const numComponents = countComponents(numAtoms, adjacency);
  const ringCount = bonds.length - numAtoms + numComponents;

  if (ringCount <= 0) return [];

  const bondIndexOf = (u, v) => {
    for (const { to, bondIdx } of adjacency[u]) {
      if (to === v) return bondIdx;
    }
    return -1;
  };

  // one candidate ring per bond: the shortest cycle through it
  const candidates = [];
  const seenAtomSets = new Set();

  bonds.forEach((bond, bondIdx) => {
    const path = shortestPathExcluding(numAtoms, adjacency, bond.start, bond.end, bondIdx);
    if (!path) return; // bond is a bridge, not part of any ring

    const key = [...path].sort((a, b) => a - b).join(",");
    if (seenAtomSets.has(key)) return;
    seenAtomSets.add(key);

    const bondIdxs = [];
    for (let i = 0; i < path.length - 1; i++) {
      bondIdxs.push(bondIndexOf(path[i], path[i + 1]));
    }
    bondIdxs.push(bondIdx); // the closing bond itself

    candidates.push({ atoms: path, bondIdxs });
  });

  candidates.sort((a, b) => a.bondIdxs.length - b.bondIdxs.length);

  // greedily keep candidates whose bond-set is linearly independent
  // (GF(2)/XOR) of the ones already kept -- an incremental XOR basis.
  const basis = [];
  const selected = [];

  for (const candidate of candidates) {
    if (selected.length >= ringCount) break;

    let vector = new Set(candidate.bondIdxs);

    for (const row of basis) {
      if (vector.has(row.pivot)) {
        vector = xorSets(vector, row.vector);
      }
    }

    if (vector.size === 0) continue; // linearly dependent on existing rings

    basis.push({ pivot: Math.min(...vector), vector });
    selected.push(candidate);
  }

  // Candidates were processed smallest-first (required for correct SSSR
  // selection), but molecule.js's annotateRings() sorts rings only by
  // aromaticity and relies on a stable sort to keep the engine's original
  // ring order among ties -- that tie order decides which ring claims a
  // shared fusion bond's (assign-once) clockwise flag, i.e. the side of an
  // inner double-bond stroke. Indigo, the mol2chemfigPy3 oracle's engine,
  // emits SSSR rings ordered by their lowest atom index; matching that here
  // keeps fused-ring double bonds (indole, corrin, ...) on the same side.
  selected.sort((a, b) => Math.min(...a.atoms) - Math.min(...b.atoms));

  return selected;
}

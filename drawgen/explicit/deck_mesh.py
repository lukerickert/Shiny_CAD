#!/usr/bin/env python3
"""
==============================================================================
DECK MESH - structured shell mesh straight from the deck model
==============================================================================
Geometry -> conformal quad mesh -> .inp with the section element sets already
in it. One command, no round trip through PrePoMax to get a mesh, and no
centroid classification afterwards: at mesh time we still know which face
belongs to which part, so the sets are exact by construction rather than
inferred.

    python -m drawgen.explicit.deck_mesh deck_model.json --size 100

Why the mesh comes out regular
------------------------------
Element size alone gives gmsh freedom to pick its own divisions per edge, so
neighbouring plates disagree, quads degenerate near imprint lines, and the
node layout changes completely whenever anything moves. Instead:

  * every break coordinate in the model (panel edges, beam lines, flange
    edges, web depths) is collected per axis, giving a set of INTERVALS;
  * each interval gets a division count, ceil(length / max size), so no
    element exceeds the size you asked for;
  * an edge spanning several intervals takes the SUM of their divisions.

Because divisions live on the intervals rather than on individual edges, the
two opposite sides of any rectangle always agree - including a web whose top
edge is chopped into segments by the members crossing it, which is precisely
the case that defeats a per-edge rule. That makes the faces transfinite
(structured), so each plate is a clean grid of quads, the mesh is conformal
across every junction, and re-generating after editing one member leaves the
rest of the layout unchanged.

Faces that are not 4-cornered fall back to unstructured meshing at the same
size and are reported - never silently.

Sections and thicknesses
------------------------
Thickness is a property of the section, not of the geometry - these are shell
midsurfaces - so it lives in the beam table and comes out in two places:

  * *MATERIAL and one *SHELL SECTION per element set, written into the single
    .inp, so the sections arrive with the mesh instead of being assigned part
    by part after import. NOT written into the --split files: every file
    would then declare the same material and section names, and the second
    import is where that shows up as an error;
  * <out>_Parameters.pmp, the PrePoMax parameter table, one entry per
    section - DECK_t, GIRDER_WEB_t, GIRDER_FLANGE_t and so on. The .inp
    format has no parameters, so the cards carry plain numbers; import the
    .pmp and point each thickness field at its parameter to drive them all
    from one table.

Both flanges of a member share one parameter: they are the same plate in the
same beam, and two numbers to keep in step is a way to get them out of step.

A TOP flange sits on the deck midplane, z = 0, and REPLACES that strip of
deck rather than being laid on top of it - the deck fragments under it are
claimed by the flange in the fuse, so the plane is tiled exactly once. That
is deliberate: <NAME>_FLANGE_t is the total thickness there, not an addition
to the deck, and nothing is counted twice. The trade is that the flange has
no offset of its own, which is the usual shell idealisation for a flange
integral with the deck. Check it on any model by summing the area of the
z = 0 elements: it comes to L * B exactly.

Options
-------
    --size 100        max element size [mm] (default 100)
    --min-div 1       minimum divisions per interval (default 1)
    --tri             leave triangles instead of recombining to quads
    --order 2         second-order elements (default 1)
    --material S355   material name on the shell sections
    --no-sections     mesh and element sets only, no *SHELL SECTION cards
    --no-pmp          skip the PrePoMax parameter file
    -o out.inp        output (default <model>_mesh.inp)
    --step out.step   also write the meshed geometry as STEP
    --no-transfinite  plain unstructured mesh, for comparison

Needs gmsh only (pip install gmsh). Units: mm, deck midplane at z = 0.
==============================================================================
"""
import argparse
import json
import math
import os
import sys
from collections import OrderedDict, defaultdict

TOL = 1e-6


# ------------------------------------------------------------------ model --
def load_model(path):
    with open(path) as fh:
        m = json.load(fh)
    missing = {"L", "B", "beams"} - set(m)
    if missing:
        sys.exit(f"{os.path.basename(path)} is missing {sorted(missing)} - "
                 f"it does not look like a deck model file.")
    return m


def model_parts(m):
    """(name, [polygons]) in build order, from the ONE definition of the
    geometry rules - deck_stepgen.deck_model. Importing it here keeps the
    mesh and the STEP from ever drifting apart."""
    # ShinyCAD port: deck_stepgen is a module of the same package
    from .deck_stepgen import Beam, deck_model
    beams = [Beam(**{k: b[k] for k in ("name", "axis", "pos", "h")},
                  bf_top=float(b.get("bf_top", 0)),
                  bf_bot=float(b.get("bf_bot", 0)),
                  t_web=float(b.get("t_web", 0)),
                  t_flange=float(b.get("t_flange", 0)))
             for b in m["beams"]]
    return deck_model(float(m["L"]), float(m["B"]), beams,
                      deck_name=m.get("deck_name", "DECK"),
                      snipe=float(m.get("snipe", 30.0)))


# --------------------------------------------------------------- divisions --
class Grid:
    """Divisions per interval, per axis.

    The whole point: a division count belongs to an INTERVAL between two
    break coordinates, not to an edge. Any edge is then the sum over the
    intervals it covers, so two opposite sides of a rectangle - even when one
    is split into several edges and the other is not - always come out equal.
    """

    def __init__(self, breaks, size, min_div=1):
        # breaks: {axis index: sorted unique coordinates}
        self.axes = {}
        for ax, xs in breaks.items():
            xs = sorted(xs)
            divs = []
            for a, b in zip(xs[:-1], xs[1:]):
                n = max(int(min_div), int(math.ceil((b - a) / size - 1e-9)))
                divs.append(n)
            self.axes[ax] = (xs, divs)

    def divisions(self, ax, a, b):
        """Total divisions for an edge running along `ax` from a to b."""
        xs, divs = self.axes[ax]
        lo, hi = (a, b) if a <= b else (b, a)
        i = self._index(xs, lo)
        j = self._index(xs, hi)
        if i is None or j is None:
            return None                     # endpoint is not a break point
        return max(1, sum(divs[i:j]))

    @staticmethod
    def _index(xs, v):
        for k, x in enumerate(xs):
            if abs(x - v) < 1e-6:
                return k
        return None

    def report(self):
        out = []
        for ax, (xs, divs) in sorted(self.axes.items()):
            out.append(f"  {'xyz'[ax]}: {len(xs)} break points, "
                       f"{len(divs)} intervals, {sum(divs)} divisions "
                       f"(finest {min(divs) if divs else 0}, "
                       f"coarsest interval {max(divs) if divs else 0})")
        return "\n".join(out)


def collect_breaks(parts):
    """Every distinct coordinate the geometry actually uses, per axis. These
    are exactly the points where a plate starts, stops or is imprinted, so an
    interval never straddles a junction."""
    breaks = {0: set(), 1: set(), 2: set()}
    for _, polys in parts:
        for poly in polys:
            for p in poly:
                for ax in (0, 1, 2):
                    breaks[ax].add(round(float(p[ax]), 6))
    return breaks


def subdivide(parts, breaks):
    """Cut every plate at the model's break lines, so each face spans exactly
    ONE interval in each direction.

    This is what makes the grid actually line up. Matching division COUNTS on
    opposite sides is not enough: a side split into segments distributes its
    nodes segment by segment, while the single edge opposite spreads the same
    number uniformly, and the cells come out sheared. Once every face is an
    elementary cell, both sides are single edges of equal length and the mesh
    is a true rectangular grid.

    Returns the same [(name, [polygons])] shape, with more, smaller polygons.
    A polygon that is not an axis-aligned rectangle is passed through whole.
    """
    out = []
    for name, polys in parts:
        cells = []
        for poly in polys:
            cells.extend(_cells(poly, breaks))
        out.append((name, cells))
    return out


def _cells(poly, breaks):
    ext = [(min(p[k] for p in poly), max(p[k] for p in poly)) for k in range(3)]
    flat = [k for k in range(3) if ext[k][1] - ext[k][0] < 1e-9]
    if len(poly) != 4 or len(flat) != 1:
        return [poly]                        # not a plane-aligned rectangle
    c = flat[0]
    u, v = [k for k in range(3) if k != c]
    cu = _cuts(breaks[u], *ext[u])
    cv = _cuts(breaks[v], *ext[v])
    if len(cu) < 3 and len(cv) < 3:
        return [poly]                        # already elementary
    const = ext[c][0]
    cells = []
    for u0, u1 in zip(cu[:-1], cu[1:]):
        for v0, v1 in zip(cv[:-1], cv[1:]):
            quad = []
            for a, b in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
                p = [0.0, 0.0, 0.0]
                p[c], p[u], p[v] = const, a, b
                quad.append(tuple(p))
            cells.append(quad)
    return cells


def _cuts(bs, lo, hi):
    """The break coordinates inside [lo, hi], endpoints included."""
    xs = sorted(x for x in bs if lo - 1e-9 < x < hi + 1e-9)
    if not xs or abs(xs[0] - lo) > 1e-9:
        xs.insert(0, lo)
    if abs(xs[-1] - hi) > 1e-9:
        xs.append(hi)
    return xs


# ----------------------------------------------------------------- meshing --
def build_and_mesh(m, size, min_div=1, recombine=True, order=1,
                   transfinite=True, step_out=None, verbose=True):
    import gmsh
    parts = model_parts(m)
    breaks = collect_breaks(parts)
    n_before = sum(len(p) for _, p in parts)
    if transfinite:
        parts = subdivide(parts, breaks)
        if verbose:
            print(f"plates cut to elementary cells: {n_before} -> "
                  f"{sum(len(p) for _, p in parts)} faces")
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("deck")

    # --- surfaces, one per source polygon, then fragment so the whole thing
    #     is conformal. gmsh's fragment hands back a parent->children map, so
    #     part ownership survives without any geometric guessing.
    tags, owner_of_input = [], []
    for pi, (_, polys) in enumerate(parts):
        for poly in polys:
            pts = [gmsh.model.occ.addPoint(*p) for p in poly]
            lines = [gmsh.model.occ.addLine(pts[i], pts[(i + 1) % len(pts)])
                     for i in range(len(pts))]
            loop = gmsh.model.occ.addCurveLoop(lines)
            tags.append(gmsh.model.occ.addPlaneSurface([loop]))
            owner_of_input.append(pi)
    gmsh.model.occ.synchronize()

    out, omap = gmsh.model.occ.fragment([(2, t) for t in tags], [])
    gmsh.model.occ.removeAllDuplicates()
    gmsh.model.occ.synchronize()

    # later part claims a shared fragment - the same rule the STEP is built
    # with, so a deeper beam's flange wins a crossing square
    owner = {}
    for in_i, children in enumerate(omap):
        for dim, tag in children:
            if dim != 2:
                continue
            owner[tag] = max(owner_of_input[in_i], owner.get(tag, -1))
    surfaces = [t for (d, t) in gmsh.model.getEntities(2)]
    unowned = [t for t in surfaces if t not in owner]
    if unowned and verbose:
        print(f"note: {len(unowned)} surface(s) had no parent and are left out "
              f"of the element sets")

    # --- transfinite: divisions from the interval grid ---------------------
    n_tf = n_fallback = 0
    if transfinite:
        grid = Grid(breaks, size, min_div)
        if verbose:
            print("interval grid:")
            print(grid.report())
        # curves first
        skipped_curves = 0
        for dim, ctag in gmsh.model.getEntities(1):
            bb = gmsh.model.getBoundingBox(1, ctag)
            lo, hi = bb[:3], bb[3:]
            ax = [i for i in range(3) if hi[i] - lo[i] > 1e-6]
            if len(ax) != 1:
                skipped_curves += 1
                continue                     # not axis aligned - leave to gmsh
            a = ax[0]
            n = grid.divisions(a, lo[a], hi[a])
            if n is None:
                skipped_curves += 1
                continue
            gmsh.model.mesh.setTransfiniteCurve(ctag, n + 1)
        # then surfaces, where the 4 CORNERS are the geometric corners of the
        # rectangle - a side may be several edges long, which is the whole
        # reason the divisions live on intervals
        for stag in surfaces:
            corners = _rect_corners(gmsh, stag)
            if corners is None:
                n_fallback += 1
                continue
            try:
                gmsh.model.mesh.setTransfiniteSurface(stag, "Left", corners)
                n_tf += 1
            except Exception:
                n_fallback += 1
        if verbose:
            print(f"transfinite: {n_tf} surface(s) structured, "
                  f"{n_fallback} left unstructured"
                  + (f", {skipped_curves} curve(s) not on the grid"
                     if skipped_curves else ""))
    gmsh.option.setNumber("Mesh.MeshSizeMin", size * 0.05)
    gmsh.option.setNumber("Mesh.MeshSizeMax", size)
    if recombine:
        gmsh.option.setNumber("Mesh.RecombineAll", 1)
        gmsh.option.setNumber("Mesh.RecombinationAlgorithm", 1)
    gmsh.model.mesh.generate(2)
    if order > 1:
        gmsh.model.mesh.setOrder(order)

    # --- element sets straight from surface ownership ----------------------
    sets = OrderedDict((name, []) for name, _ in parts)
    for stag in surfaces:
        if stag not in owner:
            continue
        name = parts[owner[stag]][0]
        for etype, etags, _ in zip(*gmsh.model.mesh.getElements(2, stag)):
            sets[name].extend(int(t) for t in etags)
    sets = OrderedDict((k, v) for k, v in sets.items() if v)

    nodes = gmsh.model.mesh.getNodes()
    stats = _quality(gmsh, surfaces)
    if step_out:
        gmsh.write(step_out)
        if verbose:
            print(f"wrote {step_out}")
    return gmsh, parts, sets, stats


def _rect_corners(gmsh, stag):
    """The 4 corner vertex tags of a rectangular face, or None if it is not
    one.

    gmsh hands back a face's boundary curves in no particular order, so the
    loop is rebuilt from vertex connectivity first. A corner is then a vertex
    where the boundary changes direction; vertices sitting mid-side - left by
    a member imprinting across the plate - are collinear and are NOT corners.
    Those are exactly the faces a per-edge division rule cannot handle and the
    interval grid can.
    """
    curves = gmsh.model.getBoundary([(2, stag)], oriented=False,
                                    recursive=False)
    if len(curves) < 4:
        return None
    # curve -> its two endpoint vertices (tag, xyz)
    ends, adj = {}, defaultdict(list)
    for _, ctag in curves:
        c = abs(int(ctag))
        vs = gmsh.model.getBoundary([(1, c)], oriented=False)
        if len(vs) != 2:
            return None                      # closed/periodic curve
        vt = [int(v[1]) for v in vs]
        ends[c] = vt
        adj[vt[0]].append(c)
        adj[vt[1]].append(c)
    if any(len(v) != 2 for v in adj.values()):
        return None                          # not a single simple loop
    # walk it
    first_c = abs(int(curves[0][1]))
    v0 = ends[first_c][0]
    order, cur_v, cur_c = [v0], v0, first_c
    for _ in range(len(ends)):
        a, b = ends[cur_c]
        nxt_v = b if a == cur_v else a
        if nxt_v == v0:
            break
        order.append(nxt_v)
        nxt_c = [c for c in adj[nxt_v] if c != cur_c]
        if not nxt_c:
            return None
        cur_v, cur_c = nxt_v, nxt_c[0]
    if len(order) != len(ends):
        return None                          # more than one loop (a hole)
    xyz = {v: list(gmsh.model.getValue(0, v, [])) for v in order}
    # corners = direction changes
    n = len(order)
    corners = []
    for i in range(n):
        p0, p1, p2 = xyz[order[i - 1]], xyz[order[i]], xyz[order[(i + 1) % n]]
        d1 = _unit([p1[k] - p0[k] for k in range(3)])
        d2 = _unit([p2[k] - p1[k] for k in range(3)])
        if d1 is None or d2 is None:
            return None
        if abs(sum(d1[k] * d2[k] for k in range(3)) - 1.0) > 1e-6:
            corners.append(order[i])
    return corners if len(corners) == 4 else None


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    if n < 1e-9:
        return None
    return [x / n for x in v]


def _close(a, b):
    return all(abs(a[i] - b[i]) < 1e-6 for i in range(3))


def _quality(gmsh, surfaces):
    """What the mesh actually came out like: element types, the longest edge
    (the check that --size was honoured), aspect ratio, and how many element
    edges are shared by 3+ plates - the welded T and cruciform junctions of a
    deck structure, which are correct here, not defects."""
    import math as _m
    counts = defaultdict(int)
    for stag in surfaces:
        types, etags, _ = gmsh.model.mesh.getElements(2, stag)
        for et, tags in zip(types, etags):
            counts[gmsh.model.mesh.getElementProperties(et)[0]] += len(tags)
    ntags, ncoords, _ = gmsh.model.mesh.getNodes()
    xyz = {int(n): ncoords[3 * i:3 * i + 3] for i, n in enumerate(ntags)}
    longest, ars, edge_use = 0.0, [], defaultdict(int)
    for et in (2, 3):
        try:
            tags, nds = gmsh.model.mesh.getElementsByType(et)
        except Exception:
            continue
        if not len(tags):
            continue
        k = 3 if et == 2 else 4
        for e in range(len(tags)):
            ring = [int(x) for x in nds[e * k:(e + 1) * k]]
            ls = []
            for i in range(k):
                a, b = ring[i], ring[(i + 1) % k]
                ls.append(_m.dist(xyz[a], xyz[b]))
                edge_use[(min(a, b), max(a, b))] += 1
            longest = max(longest, max(ls))
            if min(ls) > 0:
                ars.append(max(ls) / min(ls))
    ars.sort()
    junc = defaultdict(int)
    for v in edge_use.values():
        junc[v] += 1
    return {"counts": dict(counts), "longest_edge": longest,
            "ar_median": ars[len(ars) // 2] if ars else 0.0,
            "ar_worst": ars[-1] if ars else 0.0,
            "junctions": dict(sorted(junc.items()))}


# ----------------------------------------------------------------- writing --
ABQ_TYPE = {2: ("S3", 3), 3: ("S4", 4), 9: ("S6", 6), 16: ("S8", 8)}


def mesh_data(gmsh):
    """Pull the mesh out of gmsh once: {node id: (x,y,z)} and
    {abaqus type: {element id: [node ids]}}."""
    ntags, ncoords, _ = gmsh.model.mesh.getNodes()
    nodes = {int(n): tuple(ncoords[3 * i:3 * i + 3]) for i, n in enumerate(ntags)}
    elems = OrderedDict()
    for et, (typ, nn) in ABQ_TYPE.items():
        try:
            tags, nds = gmsh.model.mesh.getElementsByType(et)
        except Exception:
            continue
        if not len(tags):
            continue
        block = elems.setdefault(typ, OrderedDict())
        for e in range(len(tags)):
            block[int(tags[e])] = [int(x) for x in nds[e * nn:(e + 1) * nn]]
    return nodes, elems


def set_extents(gmsh, sets):
    """{set name: (zmin, zmax)} - where each section actually sits.

    Printed alongside the element counts because "the flanges are missing"
    is almost always a viewing question, not a meshing one: a top flange is
    coplanar with the deck at z = 0 by construction (shell midsurfaces), and
    webs and lower flanges hang directly beneath the deck, so a plan view
    shows a flat plate and nothing else. The z column settles it from the
    console without opening the model.
    """
    nodes, elems = mesh_data(gmsh)
    conn = {e: c for block in elems.values() for e, c in block.items()}
    out = OrderedDict()
    for name, ids in sets.items():
        zs = [nodes[n][2] for e in ids for n in conn.get(e, ())]
        out[name] = (min(zs), max(zs)) if zs else (0.0, 0.0)
    return out


DEFAULT_MATERIAL = dict(name="S355", E=210000.0, nu=0.3, rho=7.85e-9)


def section_thicknesses(m, sets=None):
    """{element set: (parameter name, thickness)} from the beam table.

    One parameter per SECTION, not per member: three beams all called BEAM
    are one BEAM_WEB_t, and the top and lower flange share BEAM_FLANGE_t -
    they are the same plate in the same member, so giving them separate
    numbers to keep in step would be a way to get them out of step.

    Returns (thickness map, list of conflict messages). A conflict is two
    members with the same name carrying different thicknesses: the section
    name they generate is shared, so only one number can win, and which one
    is not something to decide silently.
    """
    t = OrderedDict()
    src = {}
    conflicts = []

    def put(setname, param, val, where):
        if setname in t:
            if abs(t[setname][1] - val) > 1e-9:
                conflicts.append(
                    f"{setname}: {src[setname]} gives {t[setname][1]:g} mm but "
                    f"{where} gives {val:g} mm - keeping {t[setname][1]:g}")
            return
        t[setname] = (param, float(val))
        src[setname] = where

    deck = m.get("deck_name", "DECK")
    put(deck, f"{deck}_t", float(m.get("deck_t", 0.0)), "the deck thickness")
    for b in m["beams"]:
        n = b["name"]
        where = f"{n} at {float(b['pos']):g}"
        put(f"{n}_WEB", f"{n}_WEB_t", float(b.get("t_web", 0.0)), where)
        if float(b.get("bf_top", 0)) > 0:
            put(f"{n}_FLANGE", f"{n}_FLANGE_t", float(b.get("t_flange", 0.0)), where)
        if float(b.get("bf_bot", 0)) > 0:
            # same parameter as the top flange, on purpose
            put(f"{n}_LOWER_FLANGE", f"{n}_FLANGE_t",
                float(b.get("t_flange", 0.0)), where)
    if sets is not None:
        t = OrderedDict((k, v) for k, v in t.items() if k in sets)
    return t, conflicts


def write_pmp(thick, path):
    """PrePoMax parameter table: one row per section thickness.

    Same three-column semicolon layout PrePoMax exports, so it goes straight
    back in through the parameter dialog. Both flanges of a member point at
    one parameter, so the file carries each name once.
    """
    seen = OrderedDict()
    for _set, (param, val) in thick.items():
        seen.setdefault(param, val)
    with open(path, "w") as fh:
        fh.write("$Name;Value/Equation;Evaluates to\n")
        for param, val in seen.items():
            fh.write(f"{param};{val:g};{val:g}\n")
    return path, list(seen)


def section_order(thick, declared):
    """The element sets that get a section, in the order they are written.

    Order is the only thing about the sections we control. PrePoMax's .inp
    reader takes ELSET, MATERIAL and OFFSET off *SHELL SECTION and nothing
    else - the section NAME is always Section-1, Section-2 ... numbered in
    file order - so writing them in the same order the element sets appear
    makes Section-N line up with the Nth entry in the model tree instead of
    being a puzzle.
    """
    return [s for s in declared if s in thick]


def section_map(thick, declared):
    """[(PrePoMax section name, element set, parameter, thickness)]."""
    return [(f"Section-{i + 1}", s, thick[s][0], thick[s][1])
            for i, s in enumerate(section_order(thick, declared))]


def _section_lines(thick, material=None, only=None):
    """*MATERIAL + one *SHELL SECTION per element set."""
    mat = dict(DEFAULT_MATERIAL, **(material or {}))
    names = section_order(thick, only if only is not None else list(thick))
    out = ["**\n** Material and shell sections\n**\n",
           "** PrePoMax names imported sections Section-1, Section-2 ... in\n"
           "** the order below - the *SHELL SECTION keyword has no name\n"
           "** field, so this table is the key:\n**\n"]
    out += [f"**   Section-{i + 1:<2d} = {s:<22s} {thick[s][1]:g} mm "
            f"({thick[s][0]})\n" for i, s in enumerate(names)]
    out += ["**\n"
            "** Thickness is a plain number: the .inp format has no\n"
            "** parameters. The companion _Parameters.pmp carries the same\n"
            "** names, so in PrePoMax you can replace each value with its\n"
            "** parameter and drive them all from one table.\n**\n",
            f"*MATERIAL, NAME={mat['name']}\n",
            "*ELASTIC\n", f"{mat['E']:g}, {mat['nu']:g}\n",
            "*DENSITY\n", f"{mat['rho']:g}\n"]
    for i, setname in enumerate(names):
        param, val = thick[setname]
        out.append(f"** Section-{i + 1} - {param}\n")
        out.append(f"*SHELL SECTION, ELSET={setname}, MATERIAL={mat['name']}\n")
        out.append(f"{val:g}\n")
    return out


def _inp_lines(nodes, elems, sets, title, node_ids=None, elem_ids=None,
               block_elset=None, thick=None, material=None):
    """Assemble one .inp. node_ids / elem_ids restrict it to a subset while
    KEEPING the original numbering - that is what lets separate files stay
    consistent with each other, so a shared junction node carries the same id
    and coordinates in every file it appears in.

    block_elset names the set on the *ELEMENT line itself. For the split
    files that MUST be the section name and not a shared label: every file
    declaring the same 'ALL_S4' is a duplicate set name across imports, and a
    preprocessor asked to import the second one has a name it already knows.
    With the section name there, the file also needs no separate *ELSET - the
    element block IS the set, so each file declares exactly one name and no
    two files declare the same one.
    """
    lines = ["*HEADING\n", f"deck_mesh.py: {title}\n", "*NODE\n"]
    for nid in sorted(node_ids if node_ids is not None else nodes):
        x, y, z = nodes[nid]
        lines.append(f"{nid}, {x:.6f}, {y:.6f}, {z:.6f}\n")
    for typ, block in elems.items():
        ids = [e for e in block if elem_ids is None or e in elem_ids]
        if not ids:
            continue
        lines.append(f"*ELEMENT, TYPE={typ}, "
                     f"ELSET={block_elset or ('ALL_' + typ)}\n")
        for e in sorted(ids):
            lines.append(f"{e}, " + ", ".join(str(x) for x in block[e]) + "\n")
    if sets and not block_elset:
        lines.append("**\n** Section element sets\n**\n")
        for name, ids in sets.items():
            ids = sorted(ids)
            if not ids:
                continue
            lines.append(f"*ELSET, ELSET={name}\n")
            for k in range(0, len(ids), 8):
                lines.append(", ".join(str(x) for x in ids[k:k + 8]) + ",\n")
            lines[-1] = lines[-1].rstrip().rstrip(",") + "\n"
    if thick:
        # only sets this file actually declares - a section pointing at an
        # ELSET that is not in the file is an error on import
        # ordered, not a set: the order these are written in IS the section
        # numbering PrePoMax will show
        declared = [block_elset] if block_elset else list(sets or ())
        lines += _section_lines(thick, material, only=declared)
    return lines


def write_isolated_inps(gmsh, sets, out, box, tol=1e-6):
    """Cut a rectangular PATCH out of the model into its own file, leaving the
    remainder as ONE conformal mesh. Two files, one seam.

    box = (x0, y0, x1, y1) in plan. An element joins the patch when its
    centroid falls inside; everything else stays together. This is the cut for
    "replace a bay and tie it back in": splitting by SECTION instead turns
    every web/deck junction in the model into an artificial interface (632 cut
    edges on the demo deck), whereas isolating a patch cuts only the edges
    around its perimeter.

    Both files keep the original numbering, and the nodes on the seam appear in
    both with the same ids and coordinates - so the two halves still line up
    exactly, and the seam is the only place a tie (or a node merge) is needed.

    Returns (patch_path, rest_path, stats).
    """
    nodes, elems = mesh_data(gmsh)
    x0, y0, x1, y1 = (min(box[0], box[2]), min(box[1], box[3]),
                      max(box[0], box[2]), max(box[1], box[3]))
    inside = set()
    for block in elems.values():
        for eid, conn in block.items():
            pts = [nodes[n] for n in conn]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            if x0 - tol <= cx <= x1 + tol and y0 - tol <= cy <= y1 + tol:
                inside.add(eid)
    if not inside:
        raise ValueError(f"no element centroid falls inside "
                         f"x {x0:g}..{x1:g}, y {y0:g}..{y1:g} - check the box "
                         f"against the panel extents")
    allE = {e for block in elems.values() for e in block}
    outside = allE - inside
    if not outside:
        raise ValueError("the box covers the whole model - nothing would be "
                         "left to tie it to")

    def nodes_of(eids):
        return {n for block in elems.values() for e, conn in block.items()
                if e in eids for n in conn}

    stem, ext = os.path.splitext(out)
    paths = []
    for tag, eids in (("PATCH", inside), ("REST", outside)):
        nids = nodes_of(eids)
        # keep each file's section sets, restricted to the elements it holds,
        # so the patch and the remainder both stay labelled by plate
        sub = OrderedDict((nm, [e for e in ids if e in eids])
                          for nm, ids in sets.items())
        sub = OrderedDict((k, v) for k, v in sub.items() if v)
        p = f"{stem}_{tag}{ext}"
        with open(p, "w") as fh:
            fh.writelines(_inp_lines(nodes, elems, sub, os.path.basename(p),
                                     node_ids=nids, elem_ids=eids))
        paths.append((p, len(eids), len(nids), list(sub)))
    seam = len(nodes_of(inside) & nodes_of(outside))
    return paths, seam


def write_inp(gmsh, sets, out, order=1, thick=None, material=None):
    """One .inp holding the whole deck, with the section element sets - and,
    when thicknesses are given, the *MATERIAL and *SHELL SECTION cards too, so
    the sections arrive with the mesh instead of being assigned by hand."""
    nodes, elems = mesh_data(gmsh)
    with open(out, "w") as fh:
        fh.writelines(_inp_lines(nodes, elems, sets, os.path.basename(out),
                                 thick=thick, material=material))


def write_split_inps(gmsh, sets, out):
    """One .inp PER element set, so each imports as its own part.

    Each file carries only the elements of that set and only the nodes they
    use - but with the ORIGINAL numbering, so the pieces still line up: a node
    on a web/deck junction appears in both files with the same id and the same
    coordinates. That is what lets them be merged back into one connected
    model after import (PrePoMax: merge coincident nodes), and it is also why
    the shared count is reported rather than left for you to discover.

    Returns [(path, n_elements, n_nodes)] plus the shared-node count.
    """
    nodes, elems = mesh_data(gmsh)
    stem, ext = os.path.splitext(out)
    written, seen = [], defaultdict(int)
    for name, ids in sets.items():
        eids = set(ids)
        nids = {n for block in elems.values() for e, conn in block.items()
                if e in eids for n in conn}
        for n in nids:
            seen[n] += 1
        path = f"{stem}_{name}{ext}"
        with open(path, "w") as fh:
            fh.writelines(_inp_lines(nodes, elems, None,
                                     os.path.basename(path),
                                     node_ids=nids, elem_ids=eids,
                                     block_elset=name))
        written.append((path, len(eids), len(nids)))
    shared = sum(1 for c in seen.values() if c > 1)
    return written, shared


# -------------------------------------------------------------------- main --
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("Options")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", help="the *_model.json written beside the STEP")
    ap.add_argument("--size", type=float, default=100.0,
                    help="max element size [mm] (default 100)")
    ap.add_argument("--min-div", type=int, default=1,
                    help="minimum divisions per interval (default 1)")
    ap.add_argument("--tri", action="store_true", help="keep triangles")
    ap.add_argument("--order", type=int, default=1, choices=(1, 2))
    ap.add_argument("--no-transfinite", action="store_true",
                    help="plain unstructured mesh, for comparison")
    ap.add_argument("-o", "--out")
    ap.add_argument("--step", help="also write the meshed geometry as STEP")
    ap.add_argument("--isolate", nargs=4, type=float,
                    metavar=("X0", "Y0", "X1", "Y1"),
                    help="cut the rectangular patch x0 y0 x1 y1 into its own "
                         "file and leave the rest as one conformal mesh - the "
                         "cut for replacing a bay and tying it back in")
    ap.add_argument("--material", default=DEFAULT_MATERIAL["name"],
                    help=f"material name for the shell sections "
                         f"(default {DEFAULT_MATERIAL['name']})")
    ap.add_argument("--no-sections", action="store_true",
                    help="do not write *MATERIAL / *SHELL SECTION into the "
                         ".inp (mesh and element sets only)")
    ap.add_argument("--no-pmp", action="store_true",
                    help="do not write the PrePoMax _Parameters.pmp")
    ap.add_argument("--split", action="store_true",
                    help="write one .inp per element set, so each imports as "
                         "its own part (numbering is kept consistent between "
                         "them)")
    a = ap.parse_args()

    if not os.path.isfile(a.model):
        sys.exit(f"not found: {a.model}")
    m = load_model(a.model)
    out = a.out or (os.path.splitext(a.model)[0].replace("_model", "") + "_mesh.inp")
    print(f"model: {os.path.basename(a.model)}  L={m['L']:g} B={m['B']:g}  "
          f"{len(m['beams'])} beams   max element {a.size:g}")

    gmsh, parts, sets, stats = build_and_mesh(
        m, a.size, min_div=a.min_div, recombine=not a.tri, order=a.order,
        transfinite=not a.no_transfinite, step_out=a.step)
    try:
        total = sum(len(v) for v in sets.values())
        thick, conflicts = section_thicknesses(m, sets)
        ext = set_extents(gmsh, sets)
        sec_no = {s: f"Section-{i + 1}"
                  for i, s in enumerate(section_order(thick, list(sets)))}
        print(f"\n{'set':24s} {'elements':>9s}  {'z range [mm]':>18s}"
              f"  {'t [mm]':>7s}  {'section':>10s}  parameter")
        for k, v in sets.items():
            lo, hi = ext[k]
            z = (f"{lo:.0f}" if abs(hi - lo) < 1e-6
                 else f"{lo:.0f} .. {hi:.0f}")
            param, t = thick.get(k, ("", 0.0))
            ts = f"{t:g}" if t else "-"
            print(f"{k:24s} {len(v):9d}  {z:>18s}  {ts:>7s}  "
                  f"{sec_no.get(k, '-'):>10s}  {param}")
        print(f"{'TOTAL':24s} {total:9d}")
        for c in conflicts:
            print(f"WARNING: {c}")
        missing = [k for k, (_p, t) in thick.items() if t <= 0]
        if len(missing) == len(thick):
            # a model saved before thicknesses existed - writing 0 mm sections
            # and a parameter table of zeros would be worse than writing none
            thick = OrderedDict()
            print("note: this model has no thicknesses, so no sections and no "
                  ".pmp are written.\n   Fill the t_web / t_flange columns and "
                  "the deck thickness to get them.")
        elif missing:
            print(f"note: no thickness set for {', '.join(missing)} - their "
                  f"sections would be 0 mm thick, so fill the t_web / "
                  f"t_flange\n   columns (or the deck thickness) before "
                  f"solving.")
        print("   z = 0 is the deck midsurface: a top flange is coplanar with "
              "the deck and\n   webs / lower flanges hang beneath it, so from "
              "directly above the model looks\n   flat - rotate to an "
              "underside view to see them.")
        print(f"\nelements by type: {stats['counts']}")
        print(f"longest element edge: {stats['longest_edge']:.3f} mm "
              f"(limit {a.size:g})")
        print(f"aspect ratio: median {stats['ar_median']:.2f}, "
              f"worst {stats['ar_worst']:.2f}"
              + ("   (a worst ratio well above ~5 usually means a very narrow "
                 "interval - a flange edge or a snipe - against a coarse "
                 "--size)" if stats["ar_worst"] > 5 else ""))
        j = stats["junctions"]
        print(f"element edges by how many plates share them: {j}")
        print("   1 = free edge, 2 = inside a plate, 3 = a welded T junction "
              "(web meeting deck), 4 = a cruciform - 3 and 4 are expected in a "
              "deck structure, not faults")
        if stats["longest_edge"] > a.size * 1.001:
            print("WARNING: an element exceeds the requested max size - a face "
                  "fell back to unstructured meshing near a very short edge.")
        if a.isolate:
            try:
                paths, seam = write_isolated_inps(gmsh, sets, out, a.isolate)
            except ValueError as e:
                sys.exit(f"--isolate: {e}")
            print()
            for p, ne, nn, names in paths:
                print(f"wrote {os.path.basename(p):28s} {ne:6d} elements, "
                      f"{nn:6d} nodes   [{', '.join(names)}]")
            print(f"\nseam: {seam} node(s) are shared by the two files - the "
                  f"perimeter of the patch, and the ONLY place they need "
                  f"joining. They carry the same ids and coordinates in both, "
                  f"so tie the seam (or merge coincident nodes there) and the "
                  f"rest of the model stays conformal, with no artificial "
                  f"interface at any plate junction.")
        elif a.split:
            written, shared = write_split_inps(gmsh, sets, out)
            print()
            for path, ne, nn in written:
                print(f"wrote {os.path.basename(path):32s} {ne:6d} elements, "
                      f"{nn:6d} nodes")
            print(f"\n{len(written)} files, {total} elements in total.")
            print(f"{shared} node(s) appear in more than one file - the "
                  f"junctions where plates meet. They keep the same id and "
                  f"coordinates in every file, so merging coincident nodes "
                  f"after import reconnects the parts into one model; without "
                  f"that merge the parts touch but are not joined.")
        else:
            secs = None if a.no_sections else (thick or None)
            write_inp(gmsh, sets, out, order=a.order, thick=secs,
                      material=dict(DEFAULT_MATERIAL, name=a.material))
            print(f"\nwrote {out}: {total} elements, {len(sets)} element sets"
                  + (f", {len(secs)} shell sections on material {a.material}"
                     if secs else ""))
            if secs:
                print("   PrePoMax imports these as Section-1..N bound to the "
                      "ELEMENT SETS (its .inp reader\n   has no section name "
                      "and no part-name region). 'Convert to Part' DELETES "
                      "the\n   element set, which is what turns the sections "
                      "red - either leave the sets alone,\n   or repoint each "
                      "section at its From_<set> part afterwards.")
        if not a.no_pmp and thick:
            pmp, params = write_pmp(thick, os.path.splitext(out)[0]
                                    + "_Parameters.pmp")
            print(f"wrote {pmp}: {len(params)} parameter(s) "
                  f"({', '.join(params)})")
            print("   PrePoMax: File > Import > that .pmp, then point each "
                  "section thickness at its\n   parameter - the .inp itself "
                  "can only hold plain numbers.")
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    main()

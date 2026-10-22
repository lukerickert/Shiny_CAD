#!/usr/bin/env python3
"""
==============================================================================
DECK STEP GENERATOR v2 - parametric deck -> partitioned named STEP assembly
==============================================================================
Beam model: one Beam type covers flat bar / T / I via flange widths:
    Beam(name, axis, pos, h, bf_top=0, bf_bot=0)
      axis    'x' (runs along x at y=pos) or 'y' (runs along y at x=pos)
      h       web depth, deck midplane to bottom-flange midplane [mm]
      bf_top  top flange breadth; 0 = none. Lies IN the deck plane (z=0):
              deck plating is modeled between the flanges.
      bf_bot  bottom flange breadth; 0 = none (flat bar).

Crossing rules (all chosen to avoid dangling imprints, which do not survive
STEP round-trips and cannot be glued by PrePoMax):
  * webs are pre-split into full-height fields at every crossing
  * top flanges run continuous; DEEPER beams claim crossing squares
  * bottom flanges: deeper beam continuous, shallower beam snipes 'snipe' mm
    short of the crossing web (mirrors real detailing)
Equal depths: the beam listed FIRST is treated as continuous.

Parts are grouped by name: beams sharing a name merge into one component
(e.g. all "STIFF" flat bars -> STIFF_WEB). Component names use the roles the
downstream deck uses - DECK, <BEAM>_WEB, <BEAM>_FLANGE (top, in the deck
plane), <BEAM>_LOWER_FLANGE.

Every build also writes <out>_model.json: the panel size and the full beam
list. deck_elsets.py reads that manifest together with the MESHED .inp and
recreates those groups as *ELSET blocks - which is what the workflow actually
needs, because merging the parts before meshing discards the STEP component
names. Units: mm, deck midplane at z=0.
==============================================================================
"""
import json
import os
from dataclasses import dataclass, asdict

# build123d/OCC are needed only to BUILD the STEP. deck_model() below is pure
# arithmetic, and deck_mesh.py wants it without dragging in OCC (it needs
# gmsh only), so the heavy imports are deferred into the functions that use
# them rather than taken at module load.
# ShinyCAD port: cadquery replaced by build123d (same OCC kernel through OCP).
def _occ():
    import build123d as bd
    from OCP.BOPAlgo import BOPAlgo_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
    return bd, BOPAlgo_Builder, BRepBuilderAPI_Sewing

# ---------------------------------------------------------------------------

@dataclass
class Beam:
    name: str
    axis: str            # 'x' or 'y'
    pos: float
    h: float
    bf_top: float = 0.0
    bf_bot: float = 0.0
    # Plate thicknesses. They do NOT affect the geometry - these are shell
    # midsurfaces, so a thickness is a property of the section, not of the
    # face. They are carried here only so the ONE place a member is described
    # is the beam table, and so the mesh writer can emit matching *SHELL
    # SECTION cards and PrePoMax parameters instead of you retyping them.
    t_web: float = 0.0
    t_flange: float = 0.0

def rect(*pts):
    return list(pts)

# ---------------------------------------------------------------------------

def deck_model(L, B, beams, deck_name="DECK", snipe=30.0):
    """Return ordered [(part_name, [polygons])] for fuse_and_group."""
    def span(b):     return L if b.axis == 'x' else B
    def crossers(b): return [(j, c) for j, c in enumerate(beams)
                             if c.axis != b.axis and 0.0 <= c.pos <= span(b)]

    def continuous_over(a, ia, c, ic):
        return a.h > c.h or (abs(a.h - c.h) < 1e-9 and ia < ic)

    def seg(b, u0, u1, z0, z1):          # rectangle in the web plane
        if b.axis == 'x':
            return rect((u0, b.pos, z0), (u1, b.pos, z0),
                        (u1, b.pos, z1), (u0, b.pos, z1))
        return rect((b.pos, u0, z0), (b.pos, u1, z0),
                    (b.pos, u1, z1), (b.pos, u0, z1))

    def strip(b, u0, u1, z, w):          # horizontal flange strip
        # clamped to the panel extents: beams on the panel edge get a
        # one-sided flange instead of overhanging the deck
        lim = B if b.axis == 'x' else L
        p0, p1 = max(0.0, b.pos - w / 2), min(lim, b.pos + w / 2)
        if p1 - p0 < 1e-9:
            return None
        if b.axis == 'x':
            return rect((u0, p0, z), (u1, p0, z), (u1, p1, z), (u0, p1, z))
        return rect((p0, u0, z), (p1, u0, z), (p1, u1, z), (p0, u1, z))

    order, polys = [], {}
    def add(name, poly):
        if name not in polys:
            order.append(name); polys[name] = []
        polys[name].append(poly)

    add(deck_name, rect((0, 0, 0), (L, 0, 0), (L, B, 0), (0, B, 0)))

    top_flanges = []                     # (h, name, poly) -> deeper claims last
    for i, b in enumerate(beams):
        cr = crossers(b)
        xs = sorted(c.pos for _, c in cr)
        bounds = [0.0, *xs, span(b)]
        gaps = {c.pos for j, c in cr if not continuous_over(b, i, c, j)}
        deeper = [c for _, c in cr if c.h > b.h + 1e-9]
        if b.bf_bot > 0 and any(abs(c.h - b.h) < 1e-9 for _, c in cr
                                if not continuous_over(b, i, c, [j for j, cc in cr if cc is c][0])):
            pass  # equal-depth crossings handled by snipe via 'gaps'

        for u0, u1 in zip(bounds[:-1], bounds[1:]):
            if u1 - u0 > 1e-9:
                add(f"{b.name}_WEB", seg(b, u0, u1, 0.0, -b.h))

        if b.bf_bot > 0:
            for u0, u1 in zip(bounds[:-1], bounds[1:]):
                a = u0 + (snipe if u0 in gaps else 0.0)
                z = u1 - (snipe if u1 in gaps else 0.0)
                if z - a > 1e-9:
                    s = strip(b, a, z, -b.h, b.bf_bot)
                    if s: add(f"{b.name}_LOWER_FLANGE", s)

        if b.bf_top > 0:
            for u0, u1 in zip(bounds[:-1], bounds[1:]):
                if u1 - u0 > 1e-9:
                    s = strip(b, u0, u1, 0.0, b.bf_top)
                    if s:
                        top_flanges.append((b.h, f"{b.name}_FLANGE", s))

    for _, name, poly in sorted(top_flanges, key=lambda t: t[0]):
        add(name, poly)                  # deepest last -> claims crossings

    return [(n, polys[n]) for n in order]

# ---------------------------------------------------------------------------
# fuse / group / export (shared with imprint_step.py)
# ---------------------------------------------------------------------------

def _poly_face(pts):
    bd, _, _ = _occ()
    w = bd.Wire.make_polygon([bd.Vector(*p) for p in pts], close=True)
    return bd.Face(w)

def fuse_and_group(part_faces):
    """part_faces: [(name, [TopoDS faces])]. General-fuse everything; return
    per-part fragment lists. Later parts claim shared fragments."""
    _, BOPAlgo_Builder, _ = _occ()
    gf = BOPAlgo_Builder()
    inputs = []
    for pi, (_, faces) in enumerate(part_faces):
        for f in faces:
            gf.AddArgument(f); inputs.append((pi, f))
    gf.SetRunParallel(True); gf.Perform()
    if gf.HasErrors():
        raise RuntimeError("fuse failed")

    owner, frag_of = {}, {}
    for pi, f in inputs:
        images = gf.Modified(f)
        frags = list(images) if images.Size() else [f]
        for fr in frags:
            key = fr.TShape()
            owner[key] = max(pi, owner.get(key, -1))
            frag_of[key] = fr
    groups = [[] for _ in part_faces]
    for key, pi in owner.items():
        groups[pi].append(frag_of[key])
    return groups, gf.Shape()

def sew_shell(faces):
    bd, _, BRepBuilderAPI_Sewing = _occ()
    sew = BRepBuilderAPI_Sewing(1e-6)
    sew.SetNonManifoldMode(True)
    for f in faces: sew.Add(f)
    sew.Perform()
    return bd.Shape.cast(sew.SewedShape())

PALETTE = ["gray70", "steelblue3", "tan3", "tan4", "firebrick3",
           "springgreen4", "gold3", "plum3", "lightsteelblue3", "salmon3"]

def export_assembly(parts, groups, out):
    """One named, coloured component per part (STEP assembly DECK_STRUCTURE).
    Returns the component names written."""
    bd, _, _ = _occ()
    children, names = [], []
    for i, ((name, _), frags) in enumerate(zip(parts, groups)):
        if not frags:
            print(f"WARNING: part '{name}' fully claimed by later parts"); continue
        sh = sew_shell(frags)
        sh.label = name
        sh.color = bd.Color(PALETTE[i % len(PALETTE)])
        children.append(sh); names.append(name)
    asm = bd.Compound(children=children, label="DECK_STRUCTURE")
    bd.export_step(asm, out)
    print(f"wrote {out}: {len(names)} named components")
    return names

def write_model_json(L, B, beams, out, snipe=30.0, deck_name="DECK", path=None,
                     deck_t=0.0):
    """Record what was generated, next to the STEP.

    The workflow merges the parts before meshing, so the STEP component names
    do not survive into the mesh. deck_elsets.py rebuilds them from this
    manifest by classifying element centroids against the same beam lines,
    which is why the manifest must describe the geometry that was ACTUALLY
    written - hence it is emitted by build(), not by hand.
    """
    if path is None:
        path = os.path.splitext(out)[0] + "_model.json"
    with open(path, "w") as fh:
        json.dump({"L": L, "B": B, "snipe": snipe, "deck_name": deck_name,
                   "deck_t": deck_t,
                   "beams": [asdict(b) for b in beams]}, fh, indent=2)
    print(f"wrote {path}: {len(beams)} beams (input for deck_elsets.py)")
    return path


def build(part_polys, out, L=None, B=None, beams=None, snipe=30.0,
          deck_name="DECK", deck_t=0.0):
    part_faces = [(n, [_poly_face(p).wrapped for p in polys]) for n, polys in part_polys]
    groups, _ = fuse_and_group(part_faces)
    for (n, f), g in zip(part_faces, groups):
        print(f"  {n:14s} {len(f):3d} -> {len(g):3d} faces")
    names = export_assembly(part_faces, groups, out)
    # the manifest needs the beam list, which deck_model consumed - pass it in
    # to get one. Omitted (an older call) = STEP only, and say so rather than
    # writing a manifest that might not match.
    if beams is not None and L is not None and B is not None:
        write_model_json(L, B, beams, out, snipe=snipe, deck_name=deck_name,
                         deck_t=deck_t)
    else:
        print("note: no beam list passed to build() - no _model.json written, "
              "so deck_elsets.py has nothing to read. Call "
              "build(parts, out, L, B, beams) to get one.")
    return names

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    L, B = 6000.0, 4000.0
    beams = [
        # deep transverse I-girders (continuous everywhere: deepest)
        Beam("GIRDER", 'y', 2000, 500, bf_top=250, bf_bot=250, t_web=10, t_flange=14),
        Beam("GIRDER", 'y', 4000, 500, bf_top=250, bf_bot=250, t_web=10, t_flange=14),
        # longitudinal I-beams (snipe at girders)
        Beam("BEAM",   'x', 1000, 250, bf_top=120, bf_bot=120, t_web=8, t_flange=12),
        Beam("BEAM",   'x', 2000, 250, bf_top=120, bf_bot=120, t_web=8, t_flange=12),
        Beam("BEAM",   'x', 3000, 250, bf_top=120, bf_bot=120, t_web=8, t_flange=12),
        # flat-bar stiffeners (bf=0 -> web only)
        Beam("STIFF",  'x',  500, 150, t_web=6),
        Beam("STIFF",  'x', 1500, 150, t_web=6),
        Beam("STIFF",  'x', 2500, 150, t_web=6),
        Beam("STIFF",  'x', 3500, 150, t_web=6),
    ]
    build(deck_model(L, B, beams), "deck.step", L, B, beams, deck_t=8.0)

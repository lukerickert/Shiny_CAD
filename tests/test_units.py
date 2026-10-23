# -*- coding: utf-8 -*-
"""Unit tests: ISO 286 limits, thread tables (ISO 965), mate solver, view mesh."""
import math

import pytest

from conftest import plate


# --------------------------------------------------------------------------- ISO 286

@pytest.mark.parametrize("size, cls, upper, lower", [
    (20, "H7", 0.021, 0.0), (20, "g6", -0.007, -0.020), (50, "h6", 0.0, -0.016), (30, "k6", 0.015, 0.002),
    (40, "p6", 0.042, 0.026), (25, "JS7", 0.0105, -0.0105), (10, "F7", 0.028, 0.013), (100, "H8", 0.054, 0.0),
    (6, "H11", 0.075, 0.0), (80, "f7", -0.030, -0.060)])
def test_iso286_limits(size, cls, upper, lower):
    from drawgen import fits
    up, lo = fits.limits(size, cls)
    assert up == pytest.approx(upper, abs=1e-9) and lo == pytest.approx(lower, abs=1e-9)


# --------------------------------------------------------------------------- threads (ISO 261, 965)

def test_metric_profile_m8():
    from drawgen import fasteners as F
    p = F.metric_profile(8, 1.25)
    assert (p["d2"], p["d3"], p["D1"], p["drill"]) == (7.188, 6.466, 6.647, 6.8)


@pytest.mark.parametrize("d, P, dmax, dmin, d2max, d2min", [
    (3, 0.5, 2.980, 2.874, 2.655, 2.580), (5, 0.8, 4.976, 4.826, 4.456, 4.361), (8, 1.25, 7.972, 7.760, 7.160, 7.042),
    (10, 1.5, 9.968, 9.732, 8.994, 8.862), (12, 1.75, 11.966, 11.701, 10.829, 10.679), (16, 2, 15.962, 15.682, 14.663, 14.503),
    (20, 2.5, 19.958, 19.623, 18.334, 18.164), (24, 3, 23.952, 23.577, 22.003, 21.803), (30, 3.5, 29.947, 29.522, 27.674, 27.462),
    (36, 4, 35.940, 35.465, 33.342, 33.118)])
def test_external_6g(d, P, dmax, dmin, d2max, d2min):
    """Limits of 6g from ISO 965-2."""
    from drawgen import fasteners as F
    t = F.tolerance(d, P, "6g")
    assert (t["d_max"], t["d_min"], t["d2_max"], t["d2_min"]) == pytest.approx((dmax, dmin, d2max, d2min), abs=1e-6)


@pytest.mark.parametrize("d, P, D2min, D2max, D1min, D1max", [
    (8, 1.25, 7.188, 7.348, 6.647, 6.912), (10, 1.5, 9.026, 9.206, 8.376, 8.676), (20, 2.5, 18.376, 18.600, 17.294, 17.744)])
def test_internal_6H(d, P, D2min, D2max, D1min, D1max):
    """Limits of 6H from ISO 965-2."""
    from drawgen import fasteners as F
    t = F.tolerance(d, P, "6H")
    assert (t["D2_min"], t["D2_max"], t["D1_min"], t["D1_max"]) == pytest.approx((D2min, D2max, D1min, D1max), abs=1e-6)


def test_trapezoidal_tr20x4():
    from drawgen import fasteners as F
    t = F.trapezoidal_profile(20, 4)
    assert (t["d2"], t["d3"], t["D1"], t["D4"], t["h3"]) == (18.0, 15.5, 16, 20.5, 2.25)


# --------------------------------------------------------------------------- mate solver

def _solve(mates, refs, datums=None, comps=None):
    from drawgen import assembly as A
    comps = comps or [{"id": "c1", "fixed": True, "name": "BASE"},
                      {"id": "c2", "name": "MOVE", "pos": [40, 20, 7], "rot": [30, 10, 0]}]
    out, nr, msgs = A.solve_mates({"components": comps, "mates": mates}, lambda c: refs.get(c),
                                  (lambda c: datums.get(c)) if datums else None)
    return out, nr, msgs


CYL = {"kind": "cylinder", "c": [0, 0, 0], "p": [0, 0, 0], "n": [0, 0, 1], "r": 5}


def _axis_of(out, cid="c2", v=(0, 0, 1)):
    from drawgen import assembly as A
    return A._apply(A._rot_matrix(out[cid][1]), [0, 0, 0], list(v), point=False)


@pytest.mark.parametrize("flip, z", [(False, -1.0), (True, 1.0)])
def test_concentric_flip(flip, z):
    refs = {"c1": [CYL], "c2": [CYL]}
    out, nr, msgs = _solve([{"id": "m", "type": "concentric", "flip": flip, "a": {"comp": "c2", "face": 0},
                             "b": {"comp": "c1", "face": 0}}], refs)
    assert nr < 1e-6 and not msgs
    assert _axis_of(out)[2] == pytest.approx(z, abs=1e-6)


def test_coincident_planes():
    refs = {"c1": [{"kind": "plane", "c": [0, 0, 10], "n": [0, 0, 1]}], "c2": [{"kind": "plane", "c": [0, 0, 0], "n": [0, 0, -1]}]}
    out, nr, msgs = _solve([{"id": "m", "type": "coincident", "a": {"comp": "c2", "face": 0}, "b": {"comp": "c1", "face": 0}}], refs)
    assert nr < 1e-6


def test_datum_axis_distance():
    from drawgen import assembly as A
    from build123d import Box
    d = A.datum_refs(Box(10, 10, 10), [])
    out, nr, msgs = _solve([{"id": "m", "type": "distance", "value": 12, "a": {"comp": "c2", "datum": "axis:Z"},
                             "b": {"comp": "c1", "datum": "axis:Z"}}], {"c1": [], "c2": []}, {"c1": d, "c2": d})
    assert nr < 1e-6
    x, y, _ = out["c2"][0]
    assert math.hypot(x, y) == pytest.approx(12, abs=1e-5)


def test_unfixed_group_keeps_first_component_in_place():
    """No fixed component: the first component of the mated group keeps its placement, the other moves to it."""
    refs = {"c1": [{"kind": "plane", "c": [0, 0, 10], "n": [0, 0, 1]}], "c2": [{"kind": "plane", "c": [0, 0, 0], "n": [0, 0, -1]}]}
    comps = [{"id": "c1", "name": "BASE", "pos": [5, 6, 7]}, {"id": "c2", "name": "MOVE", "pos": [40, 20, 30]}]
    out, nr, msgs = _solve([{"id": "m", "type": "coincident", "a": {"comp": "c2", "face": 0}, "b": {"comp": "c1", "face": 0}}],
                           refs, comps=comps)
    assert nr < 1e-6 and "c1" not in out
    assert out["c2"][0][2] == pytest.approx(17.0, abs=1e-6)


def test_incomplete_and_lost_mates_are_skipped():
    refs = {"c1": [CYL], "c2": [CYL]}
    out, nr, msgs = _solve([
        {"id": "m1", "type": "concentric", "a": {"comp": "c2", "face": 0}, "b": {"comp": "c1", "face": 0}},
        {"id": "m2", "type": "coincident", "a": {"comp": "c2", "face": 0}, "b": None},
        {"id": "m3", "type": "coincident", "a": {"comp": "c9", "face": 0}, "b": {"comp": "c2", "face": 0}}], refs)
    assert nr < 1e-6
    assert any("not picked" in m for m in msgs) and any("deleted" in m for m in msgs)


def test_conflicting_mates_are_named():
    refs = {"c1": [{"kind": "plane", "c": [0, 0, 0], "n": [0, 0, 1]}, {"kind": "plane", "c": [0, 0, 30], "n": [0, 0, 1]}],
            "c2": [{"kind": "plane", "c": [0, 0, 0], "n": [0, 0, -1]}]}
    out, nr, msgs = _solve([
        {"id": "m1", "type": "coincident", "a": {"comp": "c2", "face": 0}, "b": {"comp": "c1", "face": 0}},
        {"id": "m2", "type": "coincident", "a": {"comp": "c2", "face": 0}, "b": {"comp": "c1", "face": 1}}], refs)
    # the second mate cannot be satisfied with the first: it is left out and named, the first is satisfied
    assert nr < 1e-6 and any("left out" in m and "MOVE / BASE" in m for m in msgs)
    assert out["c2"][0][2] == pytest.approx(0, abs=1e-6)



def test_mate_errors_within_tolerance_are_not_reported():
    """Conflicting mates 0.01 mm apart: each error is 0.005 mm (below TOL_MM), no message; 30 mm apart: the second
    mate is left out (conflict), named in one message and in detail."""
    from drawgen import assembly as A
    for gap, n_bad in ((0.01, 0), (30.0, 1)):
        refs = {"c1": [{"kind": "plane", "c": [0, 0, 0], "n": [0, 0, 1]}, {"kind": "plane", "c": [0, 0, gap], "n": [0, 0, 1]}],
                "c2": [{"kind": "plane", "c": [0, 0, 0], "n": [0, 0, -1]}]}
        asm = {"components": [{"id": "c1", "name": "BASE", "fixed": True}, {"id": "c2", "name": "MOVE"}],
               "mates": [{"id": "m1", "type": "coincident", "a": {"comp": "c2", "face": 0}, "b": {"comp": "c1", "face": 0}},
                         {"id": "m2", "type": "coincident", "a": {"comp": "c2", "face": 0}, "b": {"comp": "c1", "face": 1}}]}
        detail = {}
        out, nr, msgs = A.solve_mates(asm, lambda cid: refs[cid], None, detail)
        assert len(detail["unsatisfied"]) == n_bad
        if n_bad:
            assert len(msgs) == 1 and msgs[0].startswith("1 mate left out") and "MOVE / BASE coincident" in msgs[0]
            assert list(detail["conflicts"]) == ["m2"]
        else:
            assert msgs == []

# --------------------------------------------------------------------------- meshes

def test_part_mesh_keys_one_per_face_and_edge():
    from drawgen import part
    shape, st = part.build(plate())
    m = part.mesh(shape)
    assert len(m["face_keys"]) == len(shape.faces())
    assert len(m["edge_keys"]) == len(m["edges"]) == len(shape.edges())
    assert max(m["face_of_tri"]) == len(shape.faces()) - 1
    assert all(k is not None for k in m["face_keys"])
    assert m["face_solid"] == [0] * len(shape.faces())


def test_assembly_fast_mesh_matches_faces():
    from drawgen import assembly as A, part
    shape, st = part.build(plate())
    m = A.fast_mesh(shape)
    assert sorted(set(m["face_of_tri"])) == list(range(len(shape.faces())))
    assert len(m["edges"]) == len(shape.edges())


def test_iso286_extended_grades_and_letters():
    from drawgen import fits
    cases = [(25, "u6", 61, 48), (25, "U7", -40, -61), (25, "c11", -110, -240), (25, "C11", 240, 110),
             (50, "S7", -34, -59), (1000, "H7", 90, 0), (2000, "js12", 750, -750), (40, "a11", -310, -470),
             (100, "b11", -220, -440), (30, "H14", 520, 0), (2500, "h18", 0, -28000)]
    for size, cls, up, lo in cases:
        u, l = fits.limits(size, cls)
        assert (round(u * 1000, 1), round(l * 1000, 1)) == (up, lo), (size, cls)
    f = fits.fit(25, "H7", "u6")
    assert f["kind"] == "interference" and abs(f["clearance_min"] + 0.061) < 1e-12 and abs(f["clearance_max"] + 0.027) < 1e-12
    assert fits.fit(25, "H7", "k6")["kind"] == "transition" and fits.fit(25, "H7", "g6")["kind"] == "clearance"
    with pytest.raises(ValueError):
        fits.limits(600, "g6")            # fundamental deviations up to 500 mm


def test_deviation_text_clear_of_dimension_line():
    """Stacked deviations (ISO 129-1): the lower deviation on the baseline of the nominal value, the upper one
    above; no text closer to the dimension line than TEXT_GAP (vertical and horizontal dimensions)."""
    from drawgen import annotate
    maps = {"v": [0.0, 0.0, 1.0, 0.0, 0.0]}
    for orient, p2, pos, axis in (("v", [0, 4], [10, 2], 0), ("h", [40, 0], [20, -10], 1)):
        a = {"id": "d", "type": "linear", "view": "v", "orient": orient, "p1": [0, 0], "p2": p2, "pos": pos,
             "tol": {"mode": "dev", "plus": 0, "minus": -0.04}}
        prims = annotate.render([a], maps, {"dim_text_height_mm": 3.5})[0][2]
        texts = [p for p in prims if p[0] == "rtext"]
        assert [t[4] for t in texts] == ["4" if orient == "v" else "40", "0", "-40"]
        line = pos[axis]
        side = -1 if orient == "v" else 1          # vertical: text left of the line; horizontal: above
        for t in texts:
            assert side * (t[1 + axis] - line) >= annotate.TEXT_GAP - 1e-9, t
        main, up, lo = texts
        assert abs(lo[1 + axis] - main[1 + axis]) < 1e-9 and side * (up[1 + axis] - lo[1 + axis]) > lo[3]


def test_deviation_text_um():
    from drawgen import fits, annotate
    assert [fits.fmt_dev_um(v) for v in (0.027, 0.0, -0.04, 0.0025, -1e-7)] == ["+27", "0", "-40", "+2.5", "0"]
    a = {"type": "diameter", "center": [0, 0], "r": 7.5, "tol": {"mode": "fit", "fit": "H8"}}
    assert annotate.label(a)[1:] == ("+27", "0")
    a["tol"] = {"mode": "sym", "plus": 0.02}
    assert annotate.label(a)[0].endswith(" ±20")


def test_inch_drawing_text():
    from drawgen import annotate, part, units, drawing
    assert units.inch_text(15.0) == ".591" and units.inch_text(40.0) == "1.575" and units.inch_text(-0.018, 4) == "-.0007"
    a = {"type": "diameter", "c": [0, 0], "r": 7.5, "tol": {"mode": "fit", "fit": "H8"}}
    assert annotate.label(a, "inch") == ("Ø.591 H8", "+.0011", "-.0000")
    a = {"type": "linear", "p1": [0, 0], "p2": [40, 0], "orient": "h", "tol": {"mode": "dev", "plus": 0, "minus": -0.04}}
    assert annotate.label(a, "inch") == ("1.575", "+.0000", "-.0016")
    a["tol"] = {"mode": "sym", "plus": 0.02}
    assert annotate.label(a, "inch")[0] == "1.575 ±.0008"
    h = {"dia": 9, "tol": "H7", "cbore_dia": 15, "cbore_depth": 5, "through": True}
    assert part.callout_text(h, "inch") == "Ø.354 H7, Ø.591 counterbore .197 deep, through"
    assert part.callout_text(h) == "Ø9 H7, Ø15 counterbore 5 deep, through"
    cfg = {"fields": {"Units": "mm"}, "options": {"units": "inch"}}
    assert drawing.field_values(cfg, "x", 0.0, 1.0)["Units"] == "in"
    assert drawing.field_values({"fields": {"Units": "mm"}}, "x", 0.0, 1.0)["Units"] == "mm"
    assert units.options({"options": {"units": "yard", "keys": "left"}}) == {"units": "mm", "keys": "left"}


def test_drag_pull_moves_the_chain():
    """BASE fixed; SLIDE on BASE plane XY (slides in XY); CAM concentric with SLIDE on axis Z and coincident on
    plane XY (held relative to SLIDE). A pull of CAM by (30, -20, 50) moves SLIDE and CAM by (30, -20, 0)."""
    from drawgen import assembly as A
    pl = lambda z, n: {"kind": "plane", "c": [0, 0, z], "n": n}
    refs = {"b": [pl(0, [0, 0, 1])], "s": [pl(0, [0, 0, -1]), pl(10, [0, 0, 1]), {"kind": "cylinder", "c": [5, 5, 5], "p": [5, 5, 0], "n": [0, 0, 1], "r": 3}],
            "c": [pl(0, [0, 0, -1]), {"kind": "cylinder", "c": [0, 0, 5], "p": [0, 0, 0], "n": [0, 0, -1], "r": 3}]}
    comps = [{"id": "b", "name": "BASE", "fixed": True}, {"id": "s", "name": "SLIDE", "pos": [0, 0, 0]},
             {"id": "c", "name": "CAM", "pos": [5, 5, 10]}]
    mates = [{"id": "m1", "type": "coincident", "a": {"comp": "s", "face": 0}, "b": {"comp": "b", "face": 0}},
             {"id": "m2", "type": "coincident", "a": {"comp": "c", "face": 0}, "b": {"comp": "s", "face": 1}},
             {"id": "m3", "type": "concentric", "a": {"comp": "c", "face": 1}, "b": {"comp": "s", "face": 2}}]
    asm = {"components": comps, "mates": mates}
    out, nr, msgs = A.solve_mates(asm, lambda cid: refs[cid])
    assert nr < 1e-6 and not msgs
    for c in comps:
        if c["id"] in out:
            c["pos"], c["rot"] = out[c["id"]]
    s0, c0 = list(comps[1].get("pos")), list(comps[2].get("pos"))
    out, nr, msgs = A.solve_mates(asm, lambda cid: refs[cid], drag={"comp": "c", "delta": [30, -20, 50]})
    assert nr < 1e-6
    for cid, p0 in (("s", s0), ("c", c0)):
        assert out[cid][0] == pytest.approx([p0[0] + 30, p0[1] - 20, p0[2]], abs=1e-3)


def test_drag_pull_to_placement_turns_the_chain():
    """SPINDLE concentric with BASE (axis Z, free to turn and slide); HANDLE held to SPINDLE by a concentric and two
    coincident planes (no relative motion). A pull of HANDLE to a placement turned 30 deg about Z turns SPINDLE by
    30 deg too."""
    from drawgen import assembly as A
    cyl = lambda n: {"kind": "cylinder", "c": [0, 0, 5], "p": [0, 0, 0], "n": n, "r": 5}
    pl = lambda c, n: {"kind": "plane", "c": c, "n": n}
    refs = {"b": [cyl([0, 0, 1])],
            "s": [cyl([0, 0, -1]), cyl([0, 0, 1]), pl([10, 0, 0], [1, 0, 0]), pl([0, 0, 20], [0, 0, 1])],
            "h": [cyl([0, 0, -1]), pl([10, 0, 0], [-1, 0, 0]), pl([0, 0, 20], [0, 0, -1])]}
    comps = [{"id": "b", "name": "BASE", "fixed": True}, {"id": "s", "name": "SPINDLE"}, {"id": "h", "name": "HANDLE"}]
    mates = [{"id": "m1", "type": "concentric", "a": {"comp": "s", "face": 0}, "b": {"comp": "b", "face": 0}},
             {"id": "m2", "type": "concentric", "a": {"comp": "h", "face": 0}, "b": {"comp": "s", "face": 1}},
             {"id": "m3", "type": "coincident", "a": {"comp": "h", "face": 1}, "b": {"comp": "s", "face": 2}},
             {"id": "m4", "type": "coincident", "a": {"comp": "h", "face": 2}, "b": {"comp": "s", "face": 3}}]
    asm = {"components": comps, "mates": mates}
    out, nr, msgs = A.solve_mates(asm, lambda cid: refs[cid])
    assert nr < 1e-6 and not msgs
    for c in comps:
        if c["id"] in out:
            c["pos"], c["rot"] = out[c["id"]]
    h = comps[2]
    R0 = A._rot_matrix(h.get("rot") or [0, 0, 0])
    Rz = A._rot_matrix([0, 0, 30])
    Rt = [[sum(Rz[i][k] * R0[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    pt = A._apply(Rz, [0, 0, 0], h.get("pos") or [0, 0, 0])
    out2, nr, msgs = A.solve_mates(asm, lambda cid: refs[cid], drag={"comp": "h", "pos": pt, "rot": A._euler_of(Rt)})
    assert nr < 1e-6
    Rs0 = A._rot_matrix(comps[1].get("rot") or [0, 0, 0])
    Rs1 = A._rot_matrix(out2["s"][1])
    # SPINDLE turned about Z by 30 deg: R1 = Rz(30) R0
    Rexp = [[sum(Rz[i][k] * Rs0[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    assert max(abs(Rs1[i][j] - Rexp[i][j]) for i in range(3) for j in range(3)) < 1e-4


def test_new_mate_flipped_when_the_other_way_fails():
    """SLIDE coincident with BASE (facing), then a concentric whose axis direction only fits with Flip: the solve
    keeps it flipped (detail "flipped", message) instead of leaving it out."""
    from drawgen import assembly as A
    pl = lambda z, n: {"kind": "plane", "c": [0, 0, z], "n": n}
    refs = {"b": [pl(0, [0, 0, 1]), {"kind": "cylinder", "c": [0, 0, -5], "p": [0, 0, 0], "n": [0, 0, 1], "r": 3}],
            "s": [pl(0, [0, 0, -1]), {"kind": "cylinder", "c": [0, 0, 5], "p": [0, 0, 0], "n": [0, 0, 1], "r": 3}]}
    comps = [{"id": "b", "name": "BASE", "fixed": True}, {"id": "s", "name": "SLIDE", "pos": [3, 4, 0]}]
    mates = [{"id": "m1", "type": "coincident", "a": {"comp": "s", "face": 0}, "b": {"comp": "b", "face": 0}},
             {"id": "m2", "type": "concentric", "a": {"comp": "s", "face": 1}, "b": {"comp": "b", "face": 1}}]
    det = {}
    out, nr, msgs = A.solve_mates({"components": comps, "mates": mates}, lambda cid: refs[cid], detail=det)
    assert det["flipped"] == ["m2"] and not det["conflicts"] and nr < 1e-6
    assert any("flipped" in m for m in msgs)
    assert out["s"][0][:2] == pytest.approx([0, 0], abs=1e-6)


def test_drag_with_inexact_geometry():
    """Slightly inconsistent mates (a second base face 0.001 rad off): the residual stops at a small floor; the
    solve ends early and a drag still moves the component (the time limit is not used up by the solve)."""
    import time
    from drawgen import assembly as A
    t = 0.001
    refs = {"b": [{"kind": "plane", "c": [0, 0, 0], "n": [0, 0, 1]}, {"kind": "plane", "c": [0, 50, 10], "n": [0, math.sin(t), math.cos(t)]},
                  {"kind": "plane", "c": [0, -10, 0], "n": [0, 1, 0]}],
            "s": [{"kind": "plane", "c": [0, 0, 0], "n": [0, 0, -1]}, {"kind": "plane", "c": [0, 50, 10], "n": [0, 0, -1]},
                  {"kind": "plane", "c": [0, 0, 0], "n": [0, -1, 0]}]}
    comps = [{"id": "b", "name": "BASE", "fixed": True}, {"id": "s", "name": "SLIDE", "pos": [0, 0, 0]}]
    mates = [{"id": "m1", "type": "coincident", "a": {"comp": "s", "face": 0}, "b": {"comp": "b", "face": 0}},
             {"id": "m2", "type": "coincident", "a": {"comp": "s", "face": 1}, "b": {"comp": "b", "face": 1}},
             {"id": "m3", "type": "distance", "a": {"comp": "s", "face": 2}, "b": {"comp": "b", "face": 2}, "value": 10}]
    asm = {"components": comps, "mates": mates}
    t0 = time.time()
    out, nr, msgs = A.solve_mates(asm, lambda cid: refs[cid])
    assert time.time() - t0 < 1.0 and 0 < nr < 0.01 and not msgs
    comps[1]["pos"], comps[1]["rot"] = out["s"]
    out2, nr, msgs = A.solve_mates(asm, lambda cid: refs[cid], drag={"comp": "s", "delta": [20, 0, 0], "limit": 0.3})
    assert out2["s"][0][0] - comps[1]["pos"][0] == pytest.approx(20, abs=0.05)


def test_drag_in_group_with_conflict():
    """A group with a conflicting mate (left out): a drag still moves the component as far as the kept mates allow;
    with the conflict passed in drag["skip"] the same result without solving it again."""
    from drawgen import assembly as A
    pl = lambda z, n: {"kind": "plane", "c": [0, 0, z], "n": n}
    refs = {"b": [pl(0, [0, 0, 1]), pl(30, [0, 0, 1])], "s": [pl(0, [0, 0, -1])]}
    comps = [{"id": "b", "name": "BASE", "fixed": True}, {"id": "s", "name": "SLIDE", "pos": [0, 0, 0]}]
    mates = [{"id": "m1", "type": "coincident", "a": {"comp": "s", "face": 0}, "b": {"comp": "b", "face": 0}},
             {"id": "m2", "type": "coincident", "a": {"comp": "s", "face": 0}, "b": {"comp": "b", "face": 1}}]
    asm = {"components": comps, "mates": mates}
    for skip in ([], ["m2"]):
        det = {}
        out, nr, msgs = A.solve_mates(asm, lambda cid: refs[cid], detail=det, drag={"comp": "s", "delta": [25, -10, 40], "skip": skip})
        assert "m2" in det["conflicts"]
        assert out["s"][0] == pytest.approx([25, -10, 0], abs=1e-3)


# --------------------------------------------------------------------------- tangent, edge, vertex and gear mates

PLZ = {"kind": "plane", "c": [0, 0, 0], "n": [0, 0, 1]}


@pytest.mark.parametrize("flip, z", [(False, 5.0), (True, -5.0)])
def test_tangent_plane_cylinder(flip, z):
    from drawgen import assembly as A
    refs = {"c1": [PLZ], "c2": [CYL]}
    out, nr, msgs = _solve([{"id": "m", "type": "tangent", "flip": flip, "a": {"comp": "c2", "face": 0},
                             "b": {"comp": "c1", "face": 0}}], refs)
    assert nr < 1e-6 and not msgs
    ax = _axis_of(out)
    assert abs(ax[2]) < 1e-6                                   # axis parallel to the plane
    p = A._apply(A._rot_matrix(out["c2"][1]), out["c2"][0], [0, 0, 0])
    assert p[2] == pytest.approx(z, abs=1e-6)


@pytest.mark.parametrize("flip, d", [(False, 15.0), (True, 5.0)])
def test_tangent_two_cylinders(flip, d):
    from drawgen import assembly as A
    big = dict(CYL, r=10)
    out, nr, msgs = _solve([{"id": "m", "type": "tangent", "flip": flip, "a": {"comp": "c2", "face": 0},
                             "b": {"comp": "c1", "face": 0}}], {"c1": [big], "c2": [CYL]})
    assert nr < 1e-6
    ax = _axis_of(out)
    assert abs(abs(ax[2]) - 1) < 1e-6
    p = A._apply(A._rot_matrix(out["c2"][1]), out["c2"][0], [0, 0, 0])
    assert math.hypot(p[0], p[1]) == pytest.approx(d, abs=1e-6)


def test_edge_and_vertex_refs_and_mates():
    from drawgen import assembly as A
    from build123d import Box, Cylinder, Pos
    box = Pos(5, 5, 5) * Box(10, 10, 10)
    er, vr = A.edge_refs(box), A.vertex_refs(box)
    assert len(er) == 12 and all(r["kind"] == "line" and r["len"] == pytest.approx(10) for r in er)
    assert len(vr) == 8 and {tuple(v["c"]) for v in vr} == {(x, y, z) for x in (0, 10) for y in (0, 10) for z in (0, 10)}
    m = A.fast_mesh(box)
    assert len(m["edge_ids"]) == len(m["edges"]) == 12 and sorted(m["edge_ids"]) == list(range(12))
    cyl = Cylinder(4, 20)
    ce = [r for r in A.edge_refs(cyl) if r and r["kind"] == "circle"]
    assert len(ce) == 2 and ce[0]["r"] == pytest.approx(4)
    e = {"erefs": er, "vrefs": vr}
    geo = A.geo_refs(e)
    # vertex (10, 10, 10) of the moving box on the plane z = 0 of the base
    vi = next(i for i, v in enumerate(vr) if v["c"] == [10, 10, 10])
    out, nr, msgs = _solve([{"id": "m", "type": "coincident", "a": {"comp": "c2", "vertex": vi}, "b": {"comp": "c1", "face": 0}}],
                           {"c1": [PLZ], "c2": []}, {"c1": {}, "c2": geo})
    assert nr < 1e-6
    p = A._apply(A._rot_matrix(out["c2"][1]), out["c2"][0], [10, 10, 10])
    assert p[2] == pytest.approx(0, abs=1e-6)
    # point mate vertex to vertex
    out, nr, msgs = _solve([{"id": "m", "type": "point", "a": {"comp": "c2", "vertex": vi}, "b": {"comp": "c1", "vertex": 0}}],
                           {"c1": [], "c2": []}, {"c1": geo, "c2": geo})
    assert nr < 1e-6
    assert A._apply(A._rot_matrix(out["c2"][1]), out["c2"][0], [10, 10, 10]) == pytest.approx(vr[0]["c"], abs=1e-6)
    # an edge collinear with an edge (coincident lines), and a circular edge concentric with a cylinder
    out, nr, msgs = _solve([{"id": "m", "type": "coincident", "a": {"comp": "c2", "edge": 0}, "b": {"comp": "c1", "edge": 5}}],
                           {"c1": [], "c2": []}, {"c1": geo, "c2": geo})
    assert nr < 1e-6
    cg = A.geo_refs({"erefs": A.edge_refs(cyl), "vrefs": []})
    ck = next(k for k, r in cg.items() if r["kind"] == "circle")
    out, nr, msgs = _solve([{"id": "m", "type": "concentric", "a": {"comp": "c2", "datum": None, "edge": int(ck.split(":")[1])},
                             "b": {"comp": "c1", "face": 0}}], {"c1": [dict(CYL, p=[50, 0, 0], c=[50, 0, 0])], "c2": []}, {"c1": {}, "c2": cg})
    assert nr < 1e-6
    p = A._apply(A._rot_matrix(out["c2"][1]), out["c2"][0], [0, 0, 0])
    assert math.hypot(p[0] - 50, p[1]) == pytest.approx(0, abs=1e-6)
    with pytest.raises(ValueError):
        A._residuals({"type": "parallel"}, {"kind": "point", "c": [0, 0, 0]}, PLZ)


@pytest.mark.parametrize("flip, ang", [(False, -60.0), (True, 60.0)])
def test_gear_ratio(flip, ang):
    """Gear A (fixed, turned 30 deg about z from its reference) drives gear B on a fixed axis with ratio 2."""
    from drawgen import assembly as A
    comps = [{"id": "c0", "fixed": True, "name": "FRAME"},
             {"id": "c1", "fixed": True, "name": "GEAR_A", "rot": [0, 0, 30]},
             {"id": "c2", "name": "GEAR_B", "pos": [30, 0, 0], "rot": [0, 0, 5]}]
    refs = {"c0": [dict(CYL, p=[30, 0, 0], c=[30, 0, 0])], "c1": [dict(CYL, r=20)], "c2": [dict(CYL, r=10)]}
    mates = [{"id": "m1", "type": "concentric", "flip": True, "a": {"comp": "c2", "face": 0}, "b": {"comp": "c0", "face": 0}},
             {"id": "m2", "type": "gear", "value": 2, "flip": flip, "a": {"comp": "c1", "face": 0}, "b": {"comp": "c2", "face": 0},
              "ref": {"a": [0, 0, 0], "b": [0, 0, 0]}}]
    out, nr, msgs = _solve(mates, refs, comps=comps)
    assert nr < 1e-6, msgs
    R = A._rot_matrix(out["c2"][1])
    assert math.degrees(math.atan2(R[1][0], R[0][0])) == pytest.approx(ang, abs=1e-4)
    # without a reference the current rotations are the reference: B keeps its rotation
    m2 = dict(mates[1]); m2.pop("ref")
    out, nr, msgs = _solve([mates[0], m2], refs, comps=comps)
    assert nr < 1e-6
    R = A._rot_matrix(out["c2"][1])
    assert math.degrees(math.atan2(R[1][0], R[0][0])) == pytest.approx(5, abs=1e-4)

#!/usr/bin/env python3
"""
inertia_calc.py — rigid-body mass properties from box primitives.

Decompose an impactor into axis-aligned uniform boxes. Each box has a
name, a mass, a center position, and dimensions. The script computes:

  - total mass
  - center of gravity
  - full 3x3 inertia tensor about the assembly CG (parallel axis theorem)
  - principal values and radii of gyration
  - per-primitive contribution report (own vs transport terms)

Units are whatever you feed it, consistently. For MM_TON_S decks use
mm and tonne -> inertia in t*mm^2. For hand checks m and t are cleaner.

Input: a JSON file, or --demo for a worked example.

  {
    "units": "m, t",
    "primitives": [
      {"name": "tube",   "mass": 14.86, "center": [6.0, 0, 0], "dims": [12.0, 0.5, 0.5]},
      {"name": "flange", "mass": 1.5,   "center": [0.1, 0, 0], "dims": [0.2, 0.6, 0.6]},
      {"name": "valve",  "mass": 2.0,   "center": [9.0, 0.3, 0], "dims": [0.4, 0.3, 0.3]}
    ]
  }

Design rules (matching the deck generator conventions):
  - No silent fallbacks. Missing or malformed fields abort with the
    field name and the fix.
  - Every primitive's contribution is logged for auditability.
  - Mass is taken as given, never derived from a density guess.
"""

import argparse
import json
import math
import sys


def fail(msg: str) -> None:
    sys.exit(f"ERROR: {msg}")


def load_primitives(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail(f"input file not found: {path}. Fix: check the path.")
    except json.JSONDecodeError as e:
        fail(f"input is not valid JSON ({e}). Fix: validate the file.")

    prims = data.get("primitives")
    if not isinstance(prims, list) or not prims:
        fail("'primitives' must be a non-empty list. Fix: add at least one box.")

    out = []
    for i, p in enumerate(prims):
        label = p.get("name", f"primitive[{i}]")
        for field, n in (("mass", 1), ("center", 3), ("dims", 3)):
            if field not in p:
                fail(f"{label}: missing '{field}'. Fix: add it.")
        m = p["mass"]
        if not isinstance(m, (int, float)) or m <= 0:
            fail(f"{label}: mass must be a positive number, got {m!r}.")
        c = p["center"]
        d = p["dims"]
        for vec, fname in ((c, "center"), (d, "dims")):
            if (not isinstance(vec, list)) or len(vec) != 3 or not all(
                isinstance(v, (int, float)) for v in vec
            ):
                fail(f"{label}: '{fname}' must be [x, y, z] numbers, got {vec!r}.")
        if any(v < 0 for v in d):
            fail(f"{label}: dims must be non-negative (0 allowed = point/plate).")
        out.append({"name": str(label), "mass": float(m),
                    "center": [float(v) for v in c],
                    "dims": [float(v) for v in d]})
    return out, data.get("units", "unspecified"), load_tilt(data)


def box_own_inertia(m, dims):
    """Diagonal inertia of a uniform box about its own CG, own axes."""
    lx, ly, lz = dims
    ixx = m * (ly * ly + lz * lz) / 12.0
    iyy = m * (lx * lx + lz * lz) / 12.0
    izz = m * (lx * lx + ly * ly) / 12.0
    return ixx, iyy, izz


def compute(prims):
    M = sum(p["mass"] for p in prims)
    cg = [sum(p["mass"] * p["center"][k] for p in prims) / M for k in range(3)]

    # Full tensor about assembly CG. I = sum(I_own + m*(|d|^2 * E - d d^T))
    I = [[0.0] * 3 for _ in range(3)]
    rows = []
    for p in prims:
        ixx, iyy, izz = box_own_inertia(p["mass"], p["dims"])
        own = [[ixx, 0, 0], [0, iyy, 0], [0, 0, izz]]
        d = [p["center"][k] - cg[k] for k in range(3)]
        d2 = sum(v * v for v in d)
        m = p["mass"]
        tr = [[m * (d2 * (1 if a == b else 0) - d[a] * d[b]) for b in range(3)]
              for a in range(3)]
        for a in range(3):
            for b in range(3):
                I[a][b] += own[a][b] + tr[a][b]
        rows.append({
            "name": p["name"], "mass": m, "d": d,
            "own_diag": (ixx, iyy, izz),
            "transport_diag": (tr[0][0], tr[1][1], tr[2][2]),
        })
    return M, cg, I, rows


def principal(I):
    """Eigenvalues of symmetric 3x3 without numpy (characteristic cubic)."""
    a, b, c = I[0][0], I[1][1], I[2][2]
    d, e, f = I[0][1], I[0][2], I[1][2]
    p1 = d * d + e * e + f * f
    if p1 == 0.0:
        return sorted((a, b, c), reverse=True)
    q = (a + b + c) / 3.0
    p2 = (a - q) ** 2 + (b - q) ** 2 + (c - q) ** 2 + 2 * p1
    p = math.sqrt(p2 / 6.0)
    # B = (I - q E)/p ; r = det(B)/2 clamped to [-1, 1]
    B = [[(I[i][j] - (q if i == j else 0.0)) / p for j in range(3)] for i in range(3)]
    detB = (B[0][0] * (B[1][1] * B[2][2] - B[1][2] * B[2][1])
            - B[0][1] * (B[1][0] * B[2][2] - B[1][2] * B[2][0])
            + B[0][2] * (B[1][0] * B[2][1] - B[1][1] * B[2][0]))
    r = max(-1.0, min(1.0, detB / 2.0))
    phi = math.acos(r) / 3.0
    e1 = q + 2 * p * math.cos(phi)
    e3 = q + 2 * p * math.cos(phi + 2 * math.pi / 3.0)
    e2 = 3 * q - e1 - e3
    return sorted((e1, e2, e3), reverse=True)


def eigen_symmetric_3x3(A):
    """Jacobi eigenvalue algorithm for a symmetric 3x3.

    Returns (eigenvalues, eigenvectors) where eigenvectors[c] is the
    column-c unit eigenvector. No external dependencies.
    """
    a = [row[:] for row in A]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(100):
        off = abs(a[0][1]) + abs(a[0][2]) + abs(a[1][2])
        if off < 1e-15:
            break
        for p, q in ((0, 1), (0, 2), (1, 2)):
            if abs(a[p][q]) < 1e-20:
                continue
            theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q])
            t = math.copysign(1.0, theta) / (abs(theta) + math.sqrt(theta * theta + 1.0))
            c = 1.0 / math.sqrt(t * t + 1.0)
            s = t * c
            for k in range(3):
                akp, akq = a[k][p], a[k][q]
                a[k][p] = c * akp - s * akq
                a[k][q] = s * akp + c * akq
            for k in range(3):
                apk, aqk = a[p][k], a[q][k]
                a[p][k] = c * apk - s * aqk
                a[q][k] = s * apk + c * aqk
            for k in range(3):
                vkp, vkq = v[k][p], v[k][q]
                v[k][p] = c * vkp - s * vkq
                v[k][q] = s * vkp + c * vkq
    evals = [a[i][i] for i in range(3)]
    evecs = [[v[r][c] for r in range(3)] for c in range(3)]
    return evals, evecs


def principal_misalignment(I):
    """Single rotation angle (deg) between the current axes and the
    body's principal axes. 0 means the axes are already principal."""
    _, evecs = eigen_symmetric_3x3(I)
    V = [[evecs[c][r] for c in range(3)] for r in range(3)]  # columns = evecs
    # Greedily pair each model axis with its closest eigenvector, sign-fix.
    used = [False] * 3
    P = [[0.0] * 3 for _ in range(3)]
    for r in range(3):
        bc, bd = -1, -1.0
        for c in range(3):
            if not used[c] and abs(V[r][c]) > bd:
                bd, bc = abs(V[r][c]), c
        used[bc] = True
        for rr in range(3):
            P[rr][r] = V[rr][bc]
    for c in range(3):
        if P[c][c] < 0:
            for r in range(3):
                P[r][c] = -P[r][c]
    det = (P[0][0] * (P[1][1] * P[2][2] - P[1][2] * P[2][1])
           - P[0][1] * (P[1][0] * P[2][2] - P[1][2] * P[2][0])
           + P[0][2] * (P[1][0] * P[2][1] - P[1][1] * P[2][0]))
    if det < 0:
        for r in range(3):
            P[r][2] = -P[r][2]
    tr = P[0][0] + P[1][1] + P[2][2]
    return math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1.0) / 2.0))))


def axis_L_tilt(I):
    """For a spin about each model axis, the angle (deg) by which the
    angular momentum L = I*e points away from that axis."""
    out = []
    for i in range(3):
        Le = [I[r][i] for r in range(3)]
        mag = math.sqrt(sum(x * x for x in Le))
        c = I[i][i] / mag if mag > 0 else 1.0
        out.append(math.degrees(math.acos(max(-1.0, min(1.0, c)))))
    return out


def rotation_matrix(axis: str, deg: float):
    """Right-handed rotation by deg about a global axis X, Y, or Z."""
    a = axis.upper()
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    if a == "X":
        return [[1, 0, 0], [0, c, -s], [0, s, c]]
    if a == "Y":
        return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    if a == "Z":
        return [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    fail(f"tilt axis must be X, Y, or Z, got {axis!r}.")


def rotate_tensor(I, R):
    """I_global = R * I * R^T for a tilt of the body by R."""
    RI = [[sum(R[a][k] * I[k][b] for k in range(3)) for b in range(3)]
          for a in range(3)]
    return [[sum(RI[a][k] * R[b][k] for k in range(3)) for b in range(3)]
            for a in range(3)]


def load_tilt(data):
    """Optional 'tilt': {'axis': 'X|Y|Z', 'deg': number}. None if absent."""
    t = data.get("tilt")
    if t is None:
        return None
    if not isinstance(t, dict) or "axis" not in t or "deg" not in t:
        fail("'tilt' must be {\"axis\": \"X|Y|Z\", \"deg\": number}.")
    if not isinstance(t["deg"], (int, float)):
        fail(f"tilt deg must be a number, got {t['deg']!r}.")
    rotation_matrix(t["axis"], 0.0)  # validates axis, aborts if bad
    return {"axis": t["axis"].upper(), "deg": float(t["deg"])}


def print_tensor(I, indent="  "):
    w = 12
    lab = ("x", "y", "z")
    print(indent[:-2] + " " * 6 + "".join(f"{l:>{w}}" for l in lab))
    for a in range(3):
        print(f"{indent}{lab[a]}  " + "".join(f"{I[a][b]:>{w}.5g}"
                                              for b in range(3)))


def emit_rbody(M, cg, I, node_id=None, rbody_id=None, tilt=None):
    """Emit the mass + inertia data for an OpenRadioss /RBODY master node.

    Returns a dict of the six inertia components (global frame, about CG)
    plus mass and CG, and a formatted /RBODY block as text. If tilt is
    given as {'axis','deg'}, the tensor is rotated into the global frame
    first (the CG is unchanged by a rotation about the CG).

    Radioss /RBODY inertia line order is: Jxx Jyy Jzz Jxy Jyz Jxz
    (note: yz before xz). Values are in the deck's mass*length^2 units.
    Every emitted value is logged so the injected card is auditable.
    """
    Iuse = I
    if tilt and tilt.get("deg"):
        R = rotation_matrix(tilt["axis"], tilt["deg"])
        Iuse = rotate_tensor(I, R)

    comps = {
        "mass": M,
        "cx": cg[0], "cy": cg[1], "cz": cg[2],
        "Jxx": Iuse[0][0], "Jyy": Iuse[1][1], "Jzz": Iuse[2][2],
        "Jxy": Iuse[0][1], "Jyz": Iuse[1][2], "Jxz": Iuse[0][2],
    }

    nid = node_id if node_id is not None else "<MASTER_NODE>"
    rid = rbody_id if rbody_id is not None else "<RBODY_ID>"

    def f(x):
        return f"{x: .8E}"

    lines = [
        "# /RBODY inertia payload (global frame, about CG)",
        "# order: Jxx Jyy Jzz Jxy Jyz Jxz",
        f"/RBODY/{rid}",
        "RBODY_from_inertia_calc",
        f"# node_ID   Isens Skew  Ispher   Mass          Grnod  Ikrem ICoG Surf",
        f"{nid:>10}       0     0       0   {f(M)}      0      0    3    0",
        f"# Jxx          Jyy          Jzz          Jxy          Jyz          Jxz",
        f"{f(comps['Jxx'])} {f(comps['Jyy'])} {f(comps['Jzz'])} "
        f"{f(comps['Jxy'])} {f(comps['Jyz'])} {f(comps['Jxz'])}",
        f"# CG (place master node here): "
        f"{f(cg[0])} {f(cg[1])} {f(cg[2])}",
    ]
    return comps, "\n".join(lines)


def report(M, cg, I, rows, units):
    """Print the full mass-properties report to stdout.

    M, cg, I, rows are exactly what compute() returns; units is the label
    from the input file (a label only - nothing is ever converted).

    This body used to sit unreachable inside emit_rbody, after its return,
    so main()'s call to report() raised NameError and the CLI could not run
    on a real input file. Nothing in the body changed; it only got its def.
    """
    w = 12
    print(f"units: {units}")
    print(f"\nTotal mass : {M:.6g}")
    print(f"CG         : [{cg[0]:.6g}, {cg[1]:.6g}, {cg[2]:.6g}]")
    print("\nInertia tensor about CG:")
    lab = ("x", "y", "z")
    print(" " * 6 + "".join(f"{l:>{w}}" for l in lab))
    for a in range(3):
        print(f"  {lab[a]}  " + "".join(f"{I[a][b]:>{w}.5g}" for b in range(3)))
    off = max(abs(I[0][1]), abs(I[0][2]), abs(I[1][2]))
    diag = max(abs(I[k][k]) for k in range(3))
    print(f"\nMax product of inertia : {off:.5g} "
          f"({100*off/diag:.1f}% of max diagonal)")
    if off / diag > 0.05:
        print("  NOTE: products exceed 5% of the diagonal. Enter the full")
        print("  tensor, or align the model axes with the principal axes.")
    ev = principal(I)
    print("\nPrincipal inertias     : "
          + ", ".join(f"{v:.5g}" for v in ev))
    print("Radii of gyration k    : "
          + ", ".join(f"{math.sqrt(v / M):.5g}" for v in ev))
    mis = principal_misalignment(I)
    tl = axis_L_tilt(I)
    print(f"\nModel axes vs principal: {mis:.2f} deg "
          f"(0 = axes are principal)")
    print(f"Spin-L tilt x / y / z  : "
          f"{tl[0]:.2f} / {tl[1]:.2f} / {tl[2]:.2f} deg")
    print("\nPer-primitive contributions (diagonal terms, own + transport):")
    hdr = f"  {'name':<14}{'mass':>10}{'own Ixx':>12}{'m*d^2 Ixx':>12}" \
          f"{'own Iyy':>12}{'m*d^2 Iyy':>12}{'own Izz':>12}{'m*d^2 Izz':>12}"
    print(hdr)
    for r in rows:
        o, t = r["own_diag"], r["transport_diag"]
        print(f"  {r['name']:<14}{r['mass']:>10.4g}"
              f"{o[0]:>12.4g}{t[0]:>12.4g}"
              f"{o[1]:>12.4g}{t[1]:>12.4g}"
              f"{o[2]:>12.4g}{t[2]:>12.4g}")


DEMO = {
    "units": "m, t (multiply inertias by 1e6 for t*mm^2)",
    "primitives": [
        {"name": "tube",   "mass": 14.86, "center": [6.0, 0.0, 0.0],
         "dims": [12.0, 0.5, 0.5]},
        {"name": "flange", "mass": 1.5,   "center": [0.1, 0.0, 0.0],
         "dims": [0.2, 0.6, 0.6]},
        {"name": "valve",  "mass": 2.0,   "center": [9.0, 0.3, 0.0],
         "dims": [0.4, 0.3, 0.3]},
    ],
}


def selftest():
    """Verify against analytic solutions. Aborts on mismatch."""
    # 1. Single unit box: Ixx = m(ly^2+lz^2)/12
    M, cg, I, _ = compute([{"name": "b", "mass": 12.0,
                            "center": [5, -3, 2], "dims": [1, 2, 3]}])
    exp = (12 * (4 + 9) / 12, 12 * (1 + 9) / 12, 12 * (1 + 4) / 12)
    for k in range(3):
        assert abs(I[k][k] - exp[k]) < 1e-9, "single box diagonal mismatch"
        assert abs(cg[k] - [5, -3, 2][k]) < 1e-12, "single box CG mismatch"
    # 2. Two point-ish masses at +/- L/2: I_trans -> m*L^2/2 total
    L = 10.0
    M, cg, I, _ = compute([
        {"name": "a", "mass": 1.0, "center": [-L / 2, 0, 0], "dims": [0, 0, 0]},
        {"name": "b", "mass": 1.0, "center": [+L / 2, 0, 0], "dims": [0, 0, 0]},
    ])
    assert abs(I[1][1] - 2 * 1.0 * (L / 2) ** 2) < 1e-9, "dumbbell mismatch"
    # 3. Slender rod via 100 stacked boxes vs m*L^2/12
    n, m, L = 100, 5.0, 12.0
    prims = [{"name": f"s{i}", "mass": m / n,
              "center": [(i + 0.5) * L / n, 0, 0], "dims": [L / n, 0, 0]}
             for i in range(n)]
    M, cg, I, _ = compute(prims)
    exact = m * L * L / 12.0
    assert abs(I[1][1] - exact) / exact < 1e-9, "rod convergence mismatch"
    # 4. Symmetric layout -> zero products; asymmetric -> nonzero
    M, cg, I, _ = compute([
        {"name": "p", "mass": 2.0, "center": [1, 1, 0], "dims": [0, 0, 0]},
        {"name": "q", "mass": 2.0, "center": [-1, -1, 0], "dims": [0, 0, 0]},
    ])
    assert abs(I[0][1] + 4.0) < 1e-9, "product-of-inertia sign mismatch"
    # 5. Rotation: principal values invariant; Ixz matches closed form
    It, Ia = 248.0, 0.9
    Ibody = [[It, 0, 0], [0, It, 0], [0, 0, Ia]]
    for deg in (5.0, 10.0, 37.0):
        R = rotation_matrix("Y", deg)
        Ig = rotate_tensor(Ibody, R)
        t = math.radians(deg)
        exp_xz = (Ia - It) * math.sin(t) * math.cos(t)
        assert abs(Ig[0][2] - exp_xz) < 1e-9, "rotated Ixz mismatch"
        pv_b = principal(Ibody)
        pv_g = principal(Ig)
        assert all(abs(a - b) <= 1e-7 * max(1.0, abs(a))
                   for a, b in zip(pv_b, pv_g)), \
            "principal values changed under rotation"
        tr_b = sum(Ibody[k][k] for k in range(3))
        tr_g = sum(Ig[k][k] for k in range(3))
        assert abs(tr_b - tr_g) < 1e-9, "trace changed under rotation"
    # 6. Eigenvectors and misalignment: rotate a distinct-eigenvalue
    #    tensor by a known angle and recover it.
    Idiag = [[100.0, 0, 0], [0, 40.0, 0], [0, 0, 30.0]]
    for axis, deg in (("Z", 20.0), ("X", 15.0), ("Y", 33.0)):
        R = rotation_matrix(axis, deg)
        Ir = rotate_tensor(Idiag, R)
        assert abs(principal_misalignment(Ir) - deg) < 1e-6, \
            f"misalignment recovery ({axis},{deg})"
        ev, _ = eigen_symmetric_3x3(Ir)
        assert abs(max(ev) - 100.0) < 1e-9 and abs(min(ev) - 30.0) < 1e-9, \
            "eigenvalues wrong after rotation"
    assert principal_misalignment(Idiag) < 1e-9, "diagonal should be principal"
    Itest = [[100.0, 30.0, 0], [30.0, 100.0, 0], [0, 0, 50.0]]
    assert abs(axis_L_tilt(Itest)[0]
               - math.degrees(math.atan2(30.0, 100.0))) < 1e-9, \
        "spin-L tilt mismatch"
    print("self-test: all checks passed")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", help="JSON primitive file")
    ap.add_argument("--demo", action="store_true", help="run the worked example")
    ap.add_argument("--selftest", action="store_true", help="verify vs analytic")
    ap.add_argument("--tilt", nargs=2, metavar=("AXIS", "DEG"),
                    help="tilt the assembly about its CG, e.g. --tilt Y 10 "
                         "(overrides any 'tilt' in the JSON)")
    ap.add_argument("--rad", action="store_true",
                    help="also emit an OpenRadioss /RBODY inertia block")
    ap.add_argument("--node", default=None,
                    help="master node id for the --rad block")
    ap.add_argument("--rbody", default=None,
                    help="rbody id for the --rad block")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    tilt = None
    if args.demo:
        prims, units = DEMO["primitives"], DEMO["units"]
        print("running built-in demo (12 m pipe + flange + offset valve)\n")
    elif args.input:
        prims, units, tilt = load_primitives(args.input)
    else:
        ap.error("give an input JSON, or --demo / --selftest")

    if args.tilt:
        try:
            deg = float(args.tilt[1])
        except ValueError:
            fail(f"--tilt DEG must be a number, got {args.tilt[1]!r}.")
        tilt = {"axis": args.tilt[0].upper(), "deg": deg}

    M, cg, I, rows = compute(prims)
    report(M, cg, I, rows, units)

    if tilt and tilt["deg"] != 0.0:
        R = rotation_matrix(tilt["axis"], tilt["deg"])
        Ig = rotate_tensor(I, R)
        print(f"\nTilted {tilt['deg']:g} deg about {tilt['axis']} "
              f"(rotation about the CG; CG position unchanged):")
        print("Inertia tensor, global frame:")
        print_tensor(Ig)
        off = max(abs(Ig[0][1]), abs(Ig[0][2]), abs(Ig[1][2]))
        diag = max(abs(Ig[k][k]) for k in range(3))
        print(f"Max product of inertia : {off:.5g} "
              f"({100*off/diag:.1f}% of max diagonal)")
        if off / diag > 0.05:
            print("  NOTE: enter all six components in the deck; a"
                  " diagonal-only entry drops the products.")

    if args.rad:
        comps, block = emit_rbody(M, cg, I, node_id=args.node,
                                  rbody_id=args.rbody, tilt=tilt)
        print("\n" + block)
        print("\n# machine-readable payload:")
        print(json.dumps(comps))


if __name__ == "__main__":
    main()

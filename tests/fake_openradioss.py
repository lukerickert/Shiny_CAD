# -*- coding: utf-8 -*-
"""Stand-in for the OpenCourant executables in the tests (starter, engine, anim_to_vtk, th_to_csv).

python fake_openradioss.py <tool> <arguments of the tool>; install(folder) writes launchers named like the
OpenCourant executables (<tool>_win64.cmd on Windows, <tool>_linux64_gf elsewhere) into folder.
The engine writes 5 animation files and a T01 file; anim_to_vtk writes a legacy ASCII VTK of a 4 x 4 x 1 hexahedron
grid (10 mm cells) with Displacement, EROSION_STATUS, von Mises and a strain tensor that grow with the frame number;
th_to_csv prints the energies. FAKE_OR_FAIL=engine makes the engine stop with a RUN KILLED message."""
import os
import re
import sys
import time

TOOLS = ("starter", "engine", "anim_to_vtk", "th_to_csv")


def install(folder):
    os.makedirs(folder, exist_ok=True)
    me = os.path.abspath(__file__)
    for t in TOOLS:
        if os.name == "nt":
            p = os.path.join(folder, t + "_win64.cmd")
            with open(p, "w") as f:
                f.write('@"%s" "%s" %s %%*\r\n' % (sys.executable, me, t))
        else:
            p = os.path.join(folder, t + "_linux64_gf")
            with open(p, "w") as f:
                f.write('#!/bin/sh\nexec "%s" "%s" %s "$@"\n' % (sys.executable, me, t))
            os.chmod(p, 0o755)
    return folder


def _arg(name):
    a = sys.argv[2:]
    return a[a.index(name) + 1] if name in a else None


def starter():
    deck = _arg("-i")
    job = deck.replace("_0000.rad", "")
    print(" ** OpenRadioss STARTER (fake) **")
    print(" READING INPUT %s" % deck)
    with open(job + "_0000.out", "w") as f:
        f.write(" NODAL TIME STEP DISTRIBUTION\n")
        f.write("  -->  NODAL TIME STEP\n")
        f.write("      1.0000E-07      2.0000E-07\n")
        f.write(" INITIAL ADDED MASS ESTIMATION for /DT/NODA/CST\n")
        f.write("   DM/M at first cycle | Target time step @0.9 | Target time step @0.67\n")
        f.write("      1.000E-02        |     4.000E-07         |     3.000E-07\n")
        f.write("      2.000E-02        |     6.000E-07         |     4.500E-07\n")
        f.write("      5.000E-02        |     9.000E-07         |     7.000E-07\n")
        f.write(" WARNING: estimation only\n")
        f.write(" NORMAL TERMINATION\n")
    print(" NORMAL TERMINATION")


def engine():
    deck = _arg("-i")
    job = deck.replace("_0001.rad", "")
    tstop = 0.01
    with open(deck) as f:
        lines = f.read().splitlines()
    for i, l in enumerate(lines):
        if l.startswith("/RUN"):
            tstop = float(lines[i + 1].split()[0])
    fail = os.environ.get("FAKE_OR_FAIL") == "engine"
    n = 5
    for k in range(1, n + 1):
        t = tstop * (k - 1) / (n - 1)
        print("  NC= %6d T= %.4E DT= 1.0000E-07 ERR= -0.%d%% DM/M= %.4E" % (k * 100, t, k, 1e-4 * k))
        print("  ELAPSED TIME= %.2f s  REMAINING TIME= %.2f s" % (0.1 * k, 0.1 * (n - k)))
        with open("%sA%03d" % (job, k), "w") as f:
            f.write("fake animation %d %g\n" % (k, t))
        if fail and k == 3:
            print(" ** RUN KILLED : TOTAL MASS ERROR")
            print(" MESSAGE ID : 207")
            return 1
        sys.stdout.flush()
        time.sleep(0.05)
    with open(job + "T01", "w") as f:
        for k in range(n):
            f.write("%g\n" % (tstop * k / (n - 1)))
    with open(job + "_0001.out", "w") as f:
        f.write(" NORMAL TERMINATION\n")
    print(" NORMAL TERMINATION")
    return 0


def anim_to_vtk():
    a = sys.argv[2]
    k = int(re.search(r"A(\d+)$", a).group(1))
    with open(a) as f:
        t = float(f.read().split()[3])
    nx, ny, h = 4, 4, 10.0
    pts, disp = [], []
    for z in (0, 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                x, y = i * h, j * h
                dz = -0.5 * (k - 1) * (1 - ((x - 20) ** 2 + (y - 20) ** 2) / 800.0)
                pts.append((x, y, z * h + dz))
                disp.append((0.0, 0.0, dz))
    cells = []
    for j in range(ny):
        for i in range(nx):
            b = j * (nx + 1) + i
            u = (nx + 1) * (ny + 1)
            cells.append((b, b + 1, b + nx + 2, b + nx + 1, b + u, b + 1 + u, b + nx + 2 + u, b + nx + 1 + u))
    nc = len(cells)
    out = ["# vtk DataFile Version 3.0", "fake anim_to_vtk", "ASCII", "DATASET UNSTRUCTURED_GRID",
           "FIELD FieldData 2", "TIME 1 1 double", "%g" % t, "CYCLE 1 1 int", "%d" % (k * 100),
           "POINTS %d float" % len(pts)]
    out += ["%g %g %g" % p for p in pts]
    out.append("CELLS %d %d" % (nc, nc * 9))
    out += ["8 " + " ".join(str(v) for v in c) for c in cells]
    out.append("CELL_TYPES %d" % nc)
    out += ["12"] * nc
    out.append("POINT_DATA %d" % len(pts))
    out.append("SCALARS NODE_ID int 1")
    out.append("LOOKUP_TABLE default")
    out += [str(i + 1) for i in range(len(pts))]
    out.append("VECTORS Displacement float")
    out += ["%g %g %g" % d for d in disp]
    out.append("CELL_DATA %d" % nc)
    out.append("SCALARS ELEMENT_ID int 1")
    out.append("LOOKUP_TABLE default")
    out += [str(i + 1) for i in range(nc)]
    out.append("SCALARS PART_ID int 1")
    out.append("LOOKUP_TABLE default")
    out += ["1"] * nc
    out.append("SCALARS EROSION_STATUS float 1")
    out.append("LOOKUP_TABLE default")
    out += ["0" if (k >= 4 and i == 5) else "1" for i in range(nc)]
    out.append("SCALARS 3DELEM_Von_Mises float 1")
    out.append("LOOKUP_TABLE default")
    out += ["%g" % (10.0 * k + i) for i in range(nc)]
    out.append("TENSORS 3DELEM_Strain float")
    for i in range(nc):
        e = 0.001 * k * (1 + i % 3)
        out += ["%g 0 0" % e, "0 %g 0" % (-0.5 * e), "0 0 %g" % (-0.5 * e)]
    sys.stdout.write("\n".join(out) + "\n")


def th_to_csv():
    tf = sys.argv[2]
    with open(tf) as f:
        ts = [float(x) for x in f.read().split()]
    print('"time","INTERNAL ENERGY","KINETIC ENERGY"')
    for k, t in enumerate(ts):
        print("%g,%g,%g" % (t, 10.0 * k, 100.0 - 10.0 * k))


if __name__ == "__main__":
    tool = sys.argv[1]
    rc = {"starter": starter, "engine": engine, "anim_to_vtk": anim_to_vtk, "th_to_csv": th_to_csv}[tool]()
    sys.exit(rc or 0)

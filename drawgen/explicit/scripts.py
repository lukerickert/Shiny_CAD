"""Embedded ParaView / pvbatch / extractor script strings, factored out
of the main module. These are raw-string blobs written to disk and run
by pvbatch (which has vtk+numpy); they are never executed in-process.
"""

# ---------------------------------------------------------------------------
# Embedded principal-strain extractor (run via ParaView pvbatch, which always
# has vtk + numpy). Computes max principal TOTAL strain (eps_1) as the largest
# eigenvalue of the full 3x3 shell strain tensor at membrane/upper/lower, parses
# thickness & mesh from the filename for equation (10), checks the loaded edge,
# and writes principal_strains_summary.csv into the target folder.
# ---------------------------------------------------------------------------
_EXTRACTOR_SCRIPT = r'''
import sys, os, json, csv, re
import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

STRAIN = {"membrane": ["2DELEM_Strain_(membrane)", "Strain_(membrane)"],
          "upper":    ["2DELEM_Strain_(upper)",    "Strain_(upper)"],
          "lower":    ["2DELEM_Strain_(lower)",    "Strain_(lower)"]}
DISP = ["Displacement", "DISP", "2DNODE_Displacement"]

def principal(E9):
    N = E9.shape[0]; M = E9.reshape(N, 3, 3); M = 0.5*(M + np.transpose(M, (0, 2, 1)))
    w = np.linalg.eigvalsh(M); return w[:, 2], w[:, 0]
def read_series(p):
    d = json.load(open(p)); base = os.path.dirname(p)
    return sorted([(float(e.get("time", 0)), os.path.join(base, e["name"])) for e in d.get("files", [])])
def load(fp):
    r = vtk.vtkDataSetReader(); r.SetFileName(fp)
    r.ReadAllScalarsOn(); r.ReadAllVectorsOn(); r.ReadAllTensorsOn(); r.ReadAllFieldsOn(); r.Update()
    return r.GetOutput()
def find(grid, cands):
    cd = grid.GetCellData()
    for nm in cands:
        a = cd.GetArray(nm)
        if a is not None: return vtk_to_numpy(a), "cell"
    pd = grid.GetPointData()
    for nm in cands:
        a = pd.GetArray(nm)
        if a is not None: return vtk_to_numpy(a), "point"
    return None, None
def n9(a):
    if a is None: return None
    if a.ndim == 2 and a.shape[1] == 9: return a
    if a.ndim == 1 and a.size % 9 == 0: return a.reshape(-1, 9)
    return None
def tm(name):
    t = re.search(r"_t(\d+(?:\.\d+)?)", name, re.I); m = re.search(r"_m(\d+(?:\.\d+)?)", name, re.I)
    return (float(t.group(1)) if t else None), (float(m.group(1)) if m else None)
def case(name):
    u = name.upper(); return "CC01" if "CC01" in u else ("CC02" if "CC02" in u else "??")
def f(x):
    return ("%.4f" % x) if isinstance(x, float) else "  -  "

folder = sys.argv[1]
series = []
for dp, _d, files in os.walk(folder):
    for fn in files:
        if fn.lower().endswith(".vtk.series"): series.append(os.path.join(dp, fn))
series.sort()
if not series:
    print("No .vtk.series found under", folder); sys.exit(0)
print("epsilon_1 = max principal total strain (eigenvalue of full strain tensor)")
rows = []
for sp in series:
    fn = os.path.basename(sp); c = case(fn); t, mesh = tm(fn)
    fr = read_series(sp)
    if not fr: continue
    grid = load(fr[-1][1])
    vals = {}
    for pos, cands in STRAIN.items():
        arr, _w = find(grid, cands); E = n9(arr)
        vals[pos] = (float(np.nanmax(principal(E)[0])) if E is not None else None)
    dx = dz = None
    darr, where = find(grid, DISP)
    if darr is not None and where == "point":
        pts = vtk_to_numpy(grid.GetPoints().GetData())
        if darr.shape == pts.shape:
            orig = pts - darr; edge = orig[:, 0] > orig[:, 0].max() - 1e-3
            dx = float(np.mean(darr[edge, 0])); dz = float(np.mean(darr[edge, 2]))
    mem = vals["membrane"]; up = vals["upper"]; lo = vals["lower"]
    surf = max(up, lo) if (up is not None and lo is not None) else None
    ecrl = mem*(1 + 5*t/(3*mesh)) if (c == "CC01" and mem is not None and t and mesh) else None
    parts = ["  %s t=%s mesh=%s" % (c, t, mesh), "e1_memb="+f(mem), "e1_surf="+f(surf), "e_crl="+f(ecrl)]
    if dx is not None:
        e = "edge dx=%.2f" % dx
        if c == "CC02" and dz is not None: e += "/dz=%.2f" % dz
        parts.append(e)
    print("  ".join(parts))
    rows.append([fn, c, t, mesh, fr[-1][0], mem, up, lo, ecrl, dx, dz])
out = os.path.join(folder, "principal_strains_summary.csv")
with open(out, "w", newline="") as fcsv:
    w = csv.writer(fcsv)
    w.writerow(["file", "case", "thickness_mm", "mesh_mm", "time_s",
                "e1_membrane", "e1_upper", "e1_lower", "e_crl_local", "edge_dx", "edge_dz"])
    for r in rows:
        w.writerow([("%.6f" % v) if isinstance(v, float) else ("" if v is None else v) for v in r])
print("SUMMARY_CSV:", out)
'''

# ---------------------------------------------------------------------------
# ParaView post-processing templates (v20.50).
#
# _EPS1_PF_SCRIPT   - the Programmable Filter body computing eps1 (max
#                     principal TOTAL strain, largest eigenvalue of the full
#                     3x3 strain tensor). v20.72: element-agnostic - it scans
#                     ALL cell strain-tensor arrays, so shell stations
#                     (eps1_membrane/upper/lower) and solid tensors
#                     (eps1_solid) both work. Strain-RATE tensors and scalars
#                     (plastic strain) are excluded; scalars pass through
#                     untouched. Same maths as the pvbatch extractor above.
# _PV_SESSION_SCRIPT - the per-run <job>_pv.py written next to the results.
#                     Interactive:  paraview --script=<job>_pv.py
#                     Headless:     PV_RENDER_PNGS=1 pvbatch <job>_pv.py
#                     Reads <job>_pv.json at RUNTIME, so re-generating the
#                     manifest after a re-calibration updates the session
#                     without editing code. v20.72: colours by the best
#                     available field (eps1_solid > eps1_membrane > other
#                     eps1_* > plastic strain) and scales the LUT by
#                     color_mode - "failure": 0..lut_max (the deck's rupture
#                     strain EPSILON_T2, red = about to erode); "c208": the
#                     locked 0-0.02 screening band for shell code checks.
# _PV_MACRO_SCRIPT  - a ParaView Macros-menu script (Eps1_View) applying the
#                     eps1 filter + erosion hide + best-field colouring to the
#                     ACTIVE source, for ad-hoc sessions on decks the GUI
#                     didn't build. No manifest: LUT scales to the frame max.
# Tokens __JOB__ and __EPS1__ are substituted at write time.
# ---------------------------------------------------------------------------
_EPS1_PF_SCRIPT = r'''
import numpy as np
import traceback

inp = inputs[0]
_outv = output.VTKObject
_inv = inp.VTKObject

# Rigid-body node ids, substituted by the session script at RUNTIME (the macro
# substitutes an empty list - an ad-hoc session has no deck manifest).
RIGID_NODES = __RIGID_NODES__

# Geometry + existing attributes FIRST, so the model still renders even if the
# eps1 computation below fails. PassData gives the output its OWN attribute
# containers sharing only the array pointers - ShallowCopy would share the
# container itself, and appending eps1 would then mutate the READER's data
# mid-pipeline (tolerated by old ParaView, breaks under 5.13+/6.x caching:
# empty output, grey view, ghost "(?)" arrays).
try:
    _outv.CopyStructure(_inv)
    _outv.GetPointData().PassData(_inv.GetPointData())
    _outv.GetCellData().PassData(_inv.GetCellData())
    _outv.GetFieldData().PassData(_inv.GetFieldData())
except Exception:
    _outv.ShallowCopy(_inv)   # exotic dataset type: fall back

try:
    import re as _re
    from vtk.util.numpy_support import numpy_to_vtk as _n2v
    from vtk.util.numpy_support import vtk_to_numpy as _v2n

    # NOTE: comments, not docstrings, throughout this block - it is embedded
    # verbatim inside the session's r-triple-quoted EPS1_SCRIPT string, so a
    # triple quote here would terminate that string and break the session.

    _ncells = int(_inv.GetNumberOfCells())
    _npts = int(_inv.GetNumberOfPoints())
    print("eps1 filter: input %s, %d cells, %d points."
          % (_inv.GetClassName(), _ncells, _npts))
    if _ncells == 0:
        # v20.73: this is THE symptom of a composite (partitioned) input - the
        # top-level object holds no cells and no arrays, so everything
        # downstream reads back empty and the view goes grey. The session no
        # longer builds one, but say so loudly if a hand-made pipeline does.
        print("eps1 filter: WARNING - 0 cells at the top level. If the input is a "
              "partitioned/multiblock dataset, insert a MergeBlocks (or feed the "
              "reader directly) before this filter.")

    def _add_cell_array(values, name):
        # Deep-copied into VTK so the array cannot outlive a Python reference
        # (a shallow numpy_to_vtk hands VTK a buffer the GC may reclaim).
        a = _n2v(np.ascontiguousarray(values), deep=1)
        a.SetName(name)
        _outv.GetCellData().AddArray(a)

    def _tensor33(E):
        # Normalise any strain-tensor layout to symmetric (n,3,3), else None.
        # VTK 9.x / ParaView 6.x exposes 9-component tensors as (n,3,3); older
        # versions as (n,9); flat and 6-component (Voigt) also occur. THE
        # (n,3,3) CASE IS WHY PV 6.1 SHOWED NOTHING under the old shape check.
        E = np.asarray(E)
        if E.ndim == 1 and E.size % 9 == 0:
            E = E.reshape(-1, 9)
        if E.ndim == 3 and E.shape[1:] == (3, 3):
            return 0.5 * (E + np.transpose(E, (0, 2, 1)))
        if E.ndim == 2 and E.shape[1] == 9:
            M = E.reshape(-1, 3, 3)
            return 0.5 * (M + np.transpose(M, (0, 2, 1)))
        if E.ndim == 2 and E.shape[1] == 6:
            # symmetric Voigt xx yy zz xy yz xz with ENGINEERING shear (gamma):
            # tensor shear = gamma/2. Best-effort path for converter builds
            # that write 6 components; the primary OpenRadioss output is 9.
            n = E.shape[0]
            M = np.zeros((n, 3, 3), dtype=float)
            M[:, 0, 0] = E[:, 0]; M[:, 1, 1] = E[:, 1]; M[:, 2, 2] = E[:, 2]
            M[:, 0, 1] = M[:, 1, 0] = E[:, 3] * 0.5
            M[:, 1, 2] = M[:, 2, 1] = E[:, 4] * 0.5
            M[:, 0, 2] = M[:, 2, 0] = E[:, 5] * 0.5
            return M
        return None

    def _station(name):
        # eps1 output suffix from the source array name:
        # '2DELEM_Strain_(membrane)' -> 'membrane' (shell station in parens);
        # '3DELEM_Strain' / 'Strain'  -> 'solid'   (no station = volume tensor).
        # v20.73: the bare-word fallback covers readers/filters that strip the
        # parentheses - without it every shell station collapsed onto 'solid'
        # and the outputs came out as eps1_2delem_strain_* instead of the
        # eps1_membrane / eps1_upper / eps1_lower the session colours by.
        m = _re.search(r"\(([^)]*)\)", name)
        if m and m.group(1).strip():
            return m.group(1).strip().lower()
        u = name.upper()
        for tag in ("MEMBRANE", "UPPER", "LOWER", "MIDDLE", "MID"):
            if tag in u:
                return tag.lower()
        return "solid"

    # ---- eps1 = max principal TOTAL strain, one array per strain tensor -----
    keys = list(inp.CellData.keys())
    made, skipped, taken = [], [], set()
    # Element-agnostic scan: EVERY cell array whose name mentions strain is a
    # candidate - shell stations (2DELEM_Strain_(membrane/upper/lower)) and
    # solid tensors (3DELEM_Strain) alike. Excluded: strain RATE tensors (a
    # different quantity), our own previous eps1_* outputs, and scalars (e.g.
    # Plastic_Strain / EPSP - already directly displayable, no eigen-
    # decomposition to do; they pass through untouched via PassData).
    for nm in keys:
        u = nm.upper()
        if "STRAIN" not in u or "RATE" in u or u.startswith("EPS1"):
            continue
        arr = np.asarray(inp.CellData[nm])
        if arr.ndim == 1 or (arr.ndim == 2 and arr.shape[1] == 1):
            continue                       # scalar: not a tensor candidate
        M = _tensor33(arr)
        if M is None:
            skipped.append("%s (unexpected shape %s)" % (nm, getattr(arr, "shape", "?")))
            continue
        out_name = "eps1_" + _station(nm)
        if out_name in taken:
            # two sources map to one station: disambiguate by source name, then
            # by a numeric tail, so a name can never be silently overwritten.
            out_name = "eps1_" + _re.sub(r"[^A-Za-z0-9]+", "_", nm).strip("_").lower()
            _k = 2
            while out_name in taken:
                out_name = "eps1_%s_%d" % (_re.sub(r"[^A-Za-z0-9]+", "_", nm).strip("_").lower(), _k)
                _k += 1
        w = np.linalg.eigvalsh(M)
        _add_cell_array(w[:, 2].astype(np.float64), out_name)
        taken.add(out_name)
        made.append((out_name, nm))
    if made:
        print("eps1 filter: computed %s over %d cells (from: %s)."
              % (", ".join(n for n, _s in made), _ncells,
                 ", ".join(s for _n, s in made)))
    elif skipped:
        print("eps1 filter: strain arrays present but in an unhandled layout - nothing computed.")
    else:
        print("eps1 filter: NO strain TENSOR arrays found - nothing computed. "
              "Shells need Istrain=1 (starter) + /ANIM/SHELL/TENS/STRAIN (engine); "
              "solids need /ANIM/BRICK/TENS/STRAIN (engine). "
              "Cell arrays present: %s" % ", ".join(keys))
    if skipped:
        print("eps1 filter: skipped: " + "; ".join(skipped))

    # ---- STRUCTURAL: 1 for real elements, 0 for the rigid-body spider ------
    # anim_to_vtk writes one VTK_LINE per rigid-body secondary node (the "star"
    # from the main node to every tied node). Those lines carry no strain, wreck
    # the view, and used to be culled with ExtractCellsByType - which returns a
    # PARTITIONED dataset in ParaView 6.x and took the whole pipeline composite
    # (empty array lists, grey view, no erosion filter). Flagging them here and
    # thresholding keeps every stage a plain vtkUnstructuredGrid.
    # Per-cell type array. VTK in ParaView 6.x deprecates GetCellTypesArray()
    # in favour of GetCellTypes() (the deprecation warning opens the Output
    # Messages window); older versions have only GetCellTypesArray(), where
    # GetCellTypes() requires a vtkCellTypes argument and the bare call
    # raises. Try new name, then old, warning suppressed; a wrong-sized
    # result (a distinct-types list) is rejected by the size check.
    import warnings as _warnings
    ctypes = None
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", DeprecationWarning)
        for _getter in ("GetCellTypes", "GetCellTypesArray"):
            try:
                _ct = _v2n(getattr(_inv, _getter)()).astype(np.int32)
            except Exception:
                continue
            if _ct.size == _ncells:
                ctypes = _ct
                break
    if ctypes is None:
        ctypes = np.array([_inv.GetCellType(i) for i in range(_ncells)], dtype=np.int32)
    # VTK cell types 0..4 = empty / vertex / poly-vertex / line / poly-line
    structural = (~np.isin(ctypes, (0, 1, 2, 3, 4))).astype(np.int8)
    _add_cell_array(structural, "STRUCTURAL")
    _nlink = int(_ncells - structural.sum())
    print("eps1 filter: STRUCTURAL flag set - %d element cells, %d rigid-link line cells."
          % (int(structural.sum()), _nlink))

    # ---- RIGID_SEL: cells whose every node is a rigid-body node ------------
    # PrePoMax rigid bodies grip a /GRNOD/NODE, not a part, so there is no PID
    # to threshold on. A cell is rigid if all its points are in the deck's rigid
    # node set. The impactor reads EROSION_STATUS=0 and is culled by the erosion
    # filter - this is what lets the session show it back as a grey backdrop.
    rigid_sel = np.zeros(_ncells, dtype=np.int8)
    if RIGID_NODES and _ncells:
        idname = None
        ids = None
        _pd = _inv.GetPointData()
        for cand in ("GlobalNodeId", "NODE_ID", "Node_ID", "NODE", "vtkOriginalPointIds"):
            a = _pd.GetArray(cand)
            if a is not None:
                ids = _v2n(a).astype(np.int64).ravel()
                idname = cand
                break
        if ids is None or ids.size != _npts:
            ids = np.arange(_npts, dtype=np.int64)
            idname = "point index (no id array found)"
        pt_rigid = np.isin(ids, np.asarray(sorted(set(int(n) for n in RIGID_NODES)), dtype=np.int64))
        done = False
        try:
            _ca = _inv.GetCells()
            conn = _v2n(_ca.GetConnectivityArray()).astype(np.int64)
            offs = _v2n(_ca.GetOffsetsArray()).astype(np.int64)
            counts = np.diff(offs)
            if conn.size and counts.size == _ncells and counts.min() > 0:
                sums = np.add.reduceat(pt_rigid[conn].astype(np.int64), offs[:-1])
                rigid_sel = (sums == counts).astype(np.int8)
                done = True
        except Exception:
            done = False
        if not done:
            for ci in range(_ncells):
                c = _inv.GetCell(ci)
                n = c.GetNumberOfPoints()
                ok = n > 0
                for pi in range(n):
                    if not pt_rigid[c.GetPointId(pi)]:
                        ok = False
                        break
                rigid_sel[ci] = 1 if ok else 0
        print("eps1 filter: RIGID_SEL - %d of %d cells matched %d rigid nodes via %s."
              % (int(rigid_sel.sum()), _ncells, len(RIGID_NODES), idname))
    _add_cell_array(rigid_sel, "RIGID_SEL")
except Exception:
    print("eps1 filter FAILED (geometry preserved, eps1 arrays missing):")
    traceback.print_exc()
'''


_PV_SESSION_SCRIPT = r'''"""Auto-generated ParaView session for __JOB__
(OpenRadioss Unified Workspace). Safe to re-generate; do not hand-edit -
values come from __JOB___pv.json next to this file.

Interactive session :  paraview --script=__JOB___pv.py
Deliverable renders :  set PV_RENDER_PNGS=1, then  pvbatch __JOB___pv.py

Pipeline (v20.73 - every stage is a plain vtkUnstructuredGrid):

    __JOB__                 the .vtk.series reader
      __JOB___fields        Programmable Filter: eps1_*, STRUCTURAL, RIGID_SEL
        __JOB___structural  Threshold STRUCTURAL == 1   (rigid-link lines gone)
          __JOB___active_elements   Threshold EROSION_STATUS >= keep  [DISPLAYED]
            __JOB___over_EPSILON_T1 Threshold eps1 >= onset           [hidden]
          __JOB___rigid_context     Threshold RIGID_SEL == 1  (grey backdrop)

The old ExtractCellsByType + MergeBlocks pair is gone: in ParaView 6.x the
extract returns a PARTITIONED dataset, and when MergeBlocks did not flatten it
every downstream array lookup came back empty - no EROSION_STATUS detected, no
thresholds built, colouring fell through to a non-existent 'eps1_solid', and
the whole session rendered blank. Flagging the link cells inside the
Programmable Filter and thresholding keeps the data non-composite throughout.
"""
import os, sys, json
from paraview.simple import *

JOB = "__JOB__"
try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.getcwd()

manifest = {}
mpath = os.path.join(HERE, JOB + "_pv.json")
if os.path.isfile(mpath):
    try:
        with open(mpath) as fh:
            manifest = json.load(fh)
    except Exception as e:
        print("WARNING: could not read manifest:", e)
SCREEN = manifest.get("screen_range") or [0.0, 0.02]
ET1 = manifest.get("eps_t1")
ET2 = manifest.get("eps_t2")
EROSION_KEEP = manifest.get("erosion_keep_min", 0.5)
# Colouring mode. "failure" scales the LUT 0..rupture-strain (the deck's own
# EPSILON_T2 via lut_max) so red literally means "about to erode"; "c208" keeps
# the locked 0-0.02 screening band for shell code checks. Old manifests carry
# neither key: infer failure mode from the presence of a /FAIL/TENSSTRAIN
# harvest, which is what lut_max is built from anyway.
LUT_MAX = manifest.get("lut_max") or ET2 or ET1
COLOR_MODE = manifest.get("color_mode") or ("failure" if LUT_MAX else "c208")
RNG = ([0.0, float(LUT_MAX)] if (COLOR_MODE == "failure" and LUT_MAX) else SCREEN)
# Rigid context may be a dict {"pids":[...],"nodes":[...]} (new) or a bare list
# of pids (old manifests). Normalise both.
_rc = manifest.get("rigid_context")
if _rc is None:
    _rc = {"pids": manifest.get("rigid_context_pids") or [], "nodes": []}
elif isinstance(_rc, list):
    _rc = {"pids": _rc, "nodes": []}
RIGID_PIDS = sorted(set(int(p) for p in (_rc.get("pids") or [])))
RIGID_NODES = sorted(set(int(n) for n in (_rc.get("nodes") or [])))
SHOW_RIGID = bool(manifest.get("show_rigid_context", True))

series = os.path.join(HERE, JOB + ".vtk.series")
if not os.path.isfile(series):
    print("ERROR: %s not found - run/salvage the job first." % series)
    sys.exit(1)

reader = OpenDataFile(series)
RenameSource(JOB, reader)
view = GetActiveViewOrCreate("RenderView")

# ---------------------------------------------------------------- helpers --
def get_rep(src):
    """Show a source and return a REAL representation proxy. In the ParaView
    6.1 GUI (--script), Show() can hand back an internal wrapper FUNCTION
    instead of the representation when the source is already auto-displayed -
    rep.ColorBy then dies with \"'function' object has no attribute
    'ColorBy'\". A genuine representation proxy has .SMProxy; anything else
    gets re-acquired via GetRepresentation, which looks the existing rep up
    directly."""
    r = Show(src, view)
    if not hasattr(r, "SMProxy"):
        try:
            r = GetRepresentation(src, view)
        except Exception:
            try:
                r = GetDisplayProperties(src, view)
            except Exception:
                pass
    return r


def hide(src):
    try:
        Hide(src, view)
    except Exception:
        pass


def cell_arrays(src):
    """Names of a source's cell arrays. src.CellData is the supported accessor
    (it updates the pipeline information itself and works in ParaView 6.x,
    where the raw GetCellDataInformation() proxy call came back empty under
    pvbatch); a forced data-information query is the fallback, the same one
    the Information tab makes."""
    try:
        names = list(src.CellData.keys())
    except Exception:
        names = []
    if names:
        return names
    try:
        src.UpdatePipeline()
        cdi = src.GetDataInformation().GetCellDataInformation()
        names = [cdi.GetArrayInformation(i).GetName()
                 for i in range(cdi.GetNumberOfArrays())]
        if names:
            return names
    except Exception:
        pass
    try:
        cdi = src.GetCellDataInformation()
        return [cdi.GetArrayInformation(i).GetName() for i in range(cdi.GetNumberOfArrays())]
    except Exception:
        return []


def n_cells(src):
    try:
        src.UpdatePipeline()
        return int(src.GetDataInformation().GetNumberOfCells())
    except Exception:
        return -1


def cell_threshold(src, array, lo, hi, name):
    """Threshold on a CELL array, renamed, updated and hidden. Returns None
    (loudly) instead of a silently empty source when nothing survives, so a
    caller can fall back rather than display an empty pipeline."""
    if array not in cell_arrays(src):
        print("threshold '%s' skipped: no cell array '%s' (available: %s)."
              % (name, array, ", ".join(cell_arrays(src)) or "none"))
        return None
    try:
        t = Threshold(Input=src)
        t.Scalars = ("CELLS", array)
        try:                                   # ParaView >= 5.10
            t.LowerThreshold = float(lo)
            t.UpperThreshold = float(hi)
            t.ThresholdMethod = "Between"
        except Exception:                      # older API
            t.ThresholdRange = [float(lo), float(hi)]
        RenameSource(name, t)
        t.UpdatePipeline()
        nc = n_cells(t)
        if nc <= 0:
            print("threshold '%s' produced 0 cells (%s in [%g, %g])."
                  % (name, array, float(lo), float(hi)))
            Delete(t)
            return None
        hide(t)
        return t
    except Exception as e:
        print("threshold '%s' failed: %s" % (name, e))
        return None

# --------------------------------------------------- eps1 / flags filter ---
EPS1_SCRIPT = r"""__EPS1__"""

pf = ProgrammableFilter(Input=reader)
pf.Script = EPS1_SCRIPT.replace("__RIGID_NODES__", repr(RIGID_NODES))
try:
    pf.OutputDataSetType = "Same as Input"
except Exception:
    pass
RenameSource(JOB + "_fields", pf)
pf.UpdatePipeline()
hide(reader)
hide(pf)

# Go to the LAST frame BEFORE inspecting arrays or building thresholds.
# Deciding at t=0 left the view solid grey whenever the initial-state frame
# carries no strain tensors (geometry-only first A-file).
scene = GetAnimationScene()
try:
    scene.UpdateAnimationUsingDataTimeSteps()
except Exception:
    pass
scene.GoToLast()
try:
    _steps = list(getattr(reader, "TimestepValues", []) or [])
    pf.UpdatePipeline(_steps[-1] if _steps else None)
except Exception:
    pf.UpdatePipeline()

if n_cells(pf) <= 0:
    print("ERROR: the eps1 filter output has no cells - check the Output Messages "
          "for an 'eps1 filter' line. The session cannot build its thresholds.")

# ---- structural: drop the rigid-body link lines (plain UG, not composite) --
structural = cell_threshold(pf, "STRUCTURAL", 1, 1, JOB + "_structural")
if structural is None:
    print("NOTE: STRUCTURAL flag unavailable - rigid-body link lines stay in the view.")
    structural = pf
else:
    print("rigid-body links hidden: kept %d element cells." % n_cells(structural))

# ---- erosion: OpenRadioss keeps deleted elements as zero-value ghosts ------
main = structural
_eroded_hidden = False
active = cell_threshold(structural, "EROSION_STATUS", EROSION_KEEP, 1.0,
                        JOB + "_active_elements")
if active is not None:
    main = active
    _eroded_hidden = True
    print("erosion filter: eroded elements hidden (EROSION_STATUS >= %g kept)." % EROSION_KEEP)

hide(structural)
disp = get_rep(main)
try:
    disp.Representation = "Surface"
except Exception:
    pass
try:
    # Dark edge colour so 'Surface With Edges' shows the mesh as faint lines
    # over the colour field instead of covering it.
    disp.EdgeColor = [0.15, 0.15, 0.18]
except Exception:
    pass

# ------------------------------------------------------------- colouring ---
def pick_primary_field():
    """The field the session colours by, chosen from what the filter actually
    produced: eps1_solid on a solid deck, eps1_membrane on a shell deck, any
    other eps1_* next, and a plastic-strain scalar as the last resort when no
    strain TENSOR made it into the animation. None = nothing displayable."""
    names = cell_arrays(main)
    for cand in ("eps1_solid", "eps1_membrane"):
        if cand in names:
            return cand
    for tag in ("MEMBRANE", "SOLID"):
        for n in names:
            if n.startswith("eps1_") and tag in n.upper():
                return n
    others = sorted(n for n in names if n.startswith("eps1_"))
    if others:
        return others[0]
    for n in names:
        u = n.upper()
        if "PLASTIC" in u and "STRAIN" in u and "RATE" not in u:
            return n
    return None


def style_lut(lut, lo, hi):
    """Failure colour ramp. Light grey at zero so the model reads light
    overall, colour arriving within a few percent of the range so small
    strain concentrations are visible, red pinned at the top of the range.
    Values above the range render magenta."""
    d = float(hi) - float(lo)
    if d <= 0:
        return
    pts = []
    for f, rgb in ((0.00, (0.87, 0.87, 0.89)),
                   (0.04, (0.62, 0.76, 0.98)),
                   (0.12, (0.20, 0.50, 0.95)),
                   (0.30, (0.10, 0.75, 0.45)),
                   (0.55, (0.95, 0.85, 0.10)),
                   (0.78, (0.95, 0.55, 0.10)),
                   (1.00, (0.80, 0.05, 0.05))):
        pts += [float(lo) + f * d, rgb[0], rgb[1], rgb[2]]
    lut.RGBPoints = pts
    try:
        lut.ColorSpace = "Lab"
        lut.UseAboveRangeColor = 1
        lut.AboveRangeColor = [1.0, 0.0, 1.0]
    except Exception:
        pass


def apply_lut(name, rep=None):
    """Colour by a cell array with the mode-resolved range (failure: 0..deck
    rupture strain; c208: the locked 0-0.02 screen). Refuses to colour by a
    missing array (that is what produces the grey view + '(?)' ghost entry +
    vtkSMColorMapEditorHelper warnings) - falls back to solid colour loudly."""
    global disp
    rep = rep if rep is not None else disp
    if not name or name not in cell_arrays(main):
        avail = cell_arrays(main) or ["none"]
        print("WARNING: cell array '%s' not in the filter output - showing solid colour."
              % name)
        print("         Available cell arrays: %s" % ", ".join(avail))
        print("         Check Output Messages for an 'eps1 filter' line to see why.")
        # Clearing colouring changed API across versions and MUST NOT abort
        # the session (ColorBy(rep, None) raises under ParaView 6.1).
        for clear in (lambda: ColorBy(rep, ("CELLS", None)),
                      lambda: ColorBy(rep, None),
                      lambda: setattr(rep, "ColorArrayName", ("CELLS", ""))):
            try:
                clear()
                break
            except Exception:
                continue
        return False
    if not hasattr(rep, "SMProxy"):
        rep = disp = get_rep(main)
    ColorBy(rep, ("CELLS", name))
    lut = GetColorTransferFunction(name)
    lut.RescaleTransferFunction(RNG[0], RNG[1])
    style_lut(lut, RNG[0], RNG[1])
    try:
        lut.AutomaticRescaleRangeMode = "Never"   # range stays locked
    except Exception:
        pass
    rep.SetScalarBarVisibility(view, True)
    try:
        sb = GetScalarBar(lut, view)
        sb.Title = name
        sb.ComponentTitle = ""     # single-component: 'Magnitude' is just noise
    except Exception:
        pass
    return True


def arr_max(name):
    """Current-timestep max of a cell array from data information (no Fetch)."""
    try:
        return main.CellData[name].GetRange(0)[1]
    except Exception:
        pass
    try:
        di = main.GetCellDataInformation().GetArrayInformation(name)
        return di.GetComponentRange(0)[1] if di else None
    except Exception:
        return None


PRIMARY = pick_primary_field()
_colored = apply_lut(PRIMARY)
if not _colored:
    main.UpdatePipeline()        # one retry after a forced re-execute
    PRIMARY = pick_primary_field()
    _colored = apply_lut(PRIMARY) if PRIMARY else False
if _colored and PRIMARY and not PRIMARY.startswith("eps1_"):
    print("NOTE: no strain tensors in the animation - colouring by '%s' instead. "
          "Shells need Istrain=1 + /ANIM/SHELL/TENS/STRAIN; solids need "
          "/ANIM/BRICK/TENS/STRAIN." % PRIMARY)

# Threshold pinned to the deck's RESOLVED onset strain (EPSILON_T1) - in the
# pipeline, hidden by default: toggle it on to see only elements at/over onset.
if ET1 and PRIMARY and PRIMARY.startswith("eps1_"):
    over = cell_threshold(main, PRIMARY, float(ET1), 1e9, JOB + "_over_EPSILON_T1")
    if over is not None:
        try:
            ColorBy(get_rep(over), ("CELLS", PRIMARY))
        except Exception:
            pass
        hide(over)

# ---------------------------------------------------------- hot-spot rings -
# Red boundary rings around cells at or above hot_spot_frac of the LUT max,
# to locate small strain concentrations on a large model. The threshold value
# is fixed; ring membership follows the time slider. Set hot_spot_frac in
# <job>_pv.json to change the fraction (0 = off).
_rings_on = False
HOT_FRAC = float(manifest.get("hot_spot_frac", 0.10))
if _colored and PRIMARY and PRIMARY.startswith("eps1_") and RNG[1] > 0 and HOT_FRAC > 0:
    _hot_val = HOT_FRAC * float(RNG[1])
    hot = cell_threshold(main, PRIMARY, _hot_val, 1e9, JOB + "_hot_spots")
    if hot is None:
        print("hot spots: no cell at or above %g (%d%% of LUT max) in the last frame."
              % (_hot_val, round(100 * HOT_FRAC)))
    else:
        try:
            ring = FeatureEdges(Input=ExtractSurface(Input=hot))
            ring.BoundaryEdges = 1
            ring.FeatureEdges = 0
            ring.ManifoldEdges = 0
            ring.NonManifoldEdges = 0
            RenameSource(JOB + "_hot_spot_rings", ring)
            rd = get_rep(ring)
            for clear in (lambda: ColorBy(rd, ("CELLS", None)),
                          lambda: ColorBy(rd, None)):
                try:
                    clear()
                    break
                except Exception:
                    continue
            rd.DiffuseColor = rd.AmbientColor = [1.0, 0.1, 0.1]
            try:
                rd.LineWidth = 3.0
            except Exception:
                pass
            _rings_on = True
            print("hot spots: red rings around cells with %s >= %g (%d%% of LUT max)."
                  % (PRIMARY, _hot_val, round(100 * HOT_FRAC)))
        except Exception as e:
            print("hot-spot rings skipped:", e)

# -------------------------------------------------------- live max readout -
# Current-frame max of the primary field in the lower-left corner, updating
# with the time slider.
if _colored and PRIMARY:
    try:
        ann_max = PythonAnnotation(Input=main)
        ann_max.ArrayAssociation = "Cell Data"
        if RNG[1] > 0:
            ann_max.Expression = (
                "'max %s = %%.4g   (%%.0f%%%% of LUT max %g)' %% "
                "(input.CellData['%s'].max(), "
                "100.0 * input.CellData['%s'].max() / %g)"
                % (PRIMARY, float(RNG[1]), PRIMARY, PRIMARY, float(RNG[1])))
        else:
            ann_max.Expression = ("'max %s = %%.4g' %% input.CellData['%s'].max()"
                                  % (PRIMARY, PRIMARY))
        RenameSource(JOB + "_max_readout", ann_max)
        ad_max = get_rep(ann_max)
        try:
            ad_max.WindowLocation = "Lower Left Corner"
            ad_max.Bold = 1
        except Exception:
            pass
    except Exception as e:
        print("max readout skipped:", e)

# --------------------------------------------------------- rigid context ---
# The rigidified part(s) carry ~0 strain and read EROSION_STATUS=0, so the
# erosion filter culls them - that is the "invisible impactor". Show them back
# as a faint grey ghost off the structural source (no spider, no muddy
# overlay). Toggle with show_rigid_context in <job>_pv.json.
if SHOW_RIGID:
    rc = None
    if RIGID_NODES:
        rc = cell_threshold(structural, "RIGID_SEL", 1, 1, JOB + "_rigid_context")
        if rc is None:
            print("rigid context: no cell had all of its nodes in the deck's %d rigid "
                  "nodes - falling back to PART_ID." % len(RIGID_NODES))
    if rc is None and RIGID_PIDS and "PART_ID" in cell_arrays(structural):
        try:
            # One threshold per PID (exact even if PIDs are non-contiguous - a
            # single min..max range would wrongly sweep in unrigidified parts
            # between them), merged into one source for display.
            parts = []
            for _pid in RIGID_PIDS:
                t = Threshold(Input=structural)
                t.Scalars = ("CELLS", "PART_ID")
                try:                               # ParaView >= 5.10
                    t.LowerThreshold = float(_pid)
                    t.UpperThreshold = float(_pid)
                    t.ThresholdMethod = "Between"
                except Exception:                  # older API
                    t.ThresholdRange = [float(_pid), float(_pid)]
                parts.append(t)
            rc = AppendDatasets(Input=parts) if len(parts) > 1 else parts[0]
            RenameSource(JOB + "_rigid_context", rc)
            rc.UpdatePipeline()
            print("rigid context: PART_ID(s) %s shown as grey backdrop." % RIGID_PIDS)
        except Exception as e:
            print("rigid context (PART_ID) skipped:", e)
            rc = None
    if rc is not None:
        try:
            rcd = get_rep(rc)
            try:
                ColorBy(rcd, ("CELLS", None))
            except Exception:
                ColorBy(rcd, None)
            rcd.Representation = "Surface"
            rcd.Opacity = 0.45
            rcd.AmbientColor = rcd.DiffuseColor = [0.32, 0.32, 0.36]
            print("rigid context: %d cells shown as a grey backdrop." % n_cells(rc))
        except Exception as e:
            print("rigid context display skipped:", e)

# ------------------------------------------------------------ annotation ---
try:
    txt = Text()
    lines = [JOB]
    if ET1:
        lines.append("EPSILON_T1=%g  EPSILON_T2=%g  S_Flag=%s"
                     % (ET1, (ET2 if ET2 else ET1), manifest.get("s_flag", "?")))
    if _colored and PRIMARY:
        if COLOR_MODE == "failure" and LUT_MAX:
            lines.append("%s; LUT 0-%g = deck rupture strain (red = about to erode)"
                         % (PRIMARY, RNG[1]))
        else:
            lines.append("%s; C208 screen %g-%g" % (PRIMARY, RNG[0], RNG[1]))
        if PRIMARY.startswith("eps1_"):
            lines.append("eps1 = max principal TOTAL strain")
    if _eroded_hidden:
        lines.append("eroded elements hidden (EROSION_STATUS >= %g kept)" % EROSION_KEEP)
    if _rings_on:
        lines.append("red rings = cells >= %d%% of LUT max" % round(100 * HOT_FRAC))
    if not _colored:
        lines.append("WARNING: no displayable strain array - tensors absent in the results")
        lines.append("(shells: Istrain=1; solids: /ANIM/BRICK/TENS/STRAIN). See Output Messages.")
    txt.Text = "\n".join(lines)
    adisp = get_rep(txt)
    try:
        adisp.WindowLocation = "Upper Left Corner"
    except Exception:
        pass
except Exception as e:
    print("Annotation skipped:", e)

SetActiveSource(main)
view.ResetCamera()
Render()

# -------------------- headless deliverable renders (pvbatch) ---------------
if os.environ.get("PV_RENDER_PNGS"):
    view.ViewSize = [1600, 900]
    steps = list(getattr(reader, "TimestepValues", []) or [])

    scene.GoToLast()
    main.UpdatePipeline()
    # Deliverables at the last frame: one PNG per eps1 field the filter
    # actually produced - eps1_solid on solid decks, membrane/upper/lower on
    # shells - plus the PRIMARY fallback (plastic strain) if no tensor made it
    # into the animation.
    render_fields = sorted(n for n in cell_arrays(main) if n.startswith("eps1_"))
    if not render_fields and PRIMARY:
        render_fields = [PRIMARY]
    for name in render_fields:
        if not apply_lut(name):
            print("skip render: %s not present (strain output missing)" % name)
            continue
        Render()
        out = os.path.join(HERE, "%s_%s_last.png" % (JOB, name))
        SaveScreenshot(out, view)
        print("wrote %s" % out)

    # Peak-PRIMARY frame: scan every timestep via data information (cheap - no
    # geometry fetch) and render the worst one. On an eroding model the peak
    # usually sits just BEFORE rupture unzips the section - often the most
    # informative single frame of the run.
    if steps and PRIMARY and arr_max(PRIMARY) is not None:
        best_t, best_v = None, -1e30
        for t in steps:
            try:
                scene.AnimationTime = t
            except Exception:
                pass
            main.UpdatePipeline(t)
            v = arr_max(PRIMARY)
            if v is not None and v > best_v:
                best_v, best_t = v, t
        if best_t is not None:
            try:
                scene.AnimationTime = best_t
            except Exception:
                pass
            main.UpdatePipeline(best_t)
            apply_lut(PRIMARY)
            Render()
            out = os.path.join(HERE, "%s_%s_peak.png" % (JOB, PRIMARY))
            SaveScreenshot(out, view)
            print("wrote %s (t=%g, max %s=%.5f)" % (out, best_t, PRIMARY, best_v))
    print("PV render complete.")
'''

_PV_MACRO_SCRIPT = r'''"""Eps1_View - ParaView macro (OpenRadioss Unified Workspace, v20.73).
Adds the max-principal-TOTAL-strain (eps1) Programmable Filter to the ACTIVE
source - shells AND solids - drops the rigid-body link lines, hides eroded
elements, and colours by the best available field (eps1_solid > eps1_membrane >
other eps1_* > plastic strain). Ad-hoc sessions have no deck manifest, so the
LUT is scaled 0..current-frame max (fallback 0-0.02 if the field is flat) and
there is no rigid node list. Same eps1 maths as the per-run sessions."""
from paraview.simple import *

src = GetActiveSource()
if src is None:
    print("Eps1_View: select a source in the Pipeline Browser first.")
else:
    EPS1_SCRIPT = r"""__EPS1__"""
    view = GetActiveViewOrCreate("RenderView")
    pf = ProgrammableFilter(Input=src)
    pf.Script = EPS1_SCRIPT.replace("__RIGID_NODES__", "[]")
    try:
        pf.OutputDataSetType = "Same as Input"
    except Exception:
        pass
    RenameSource("eps1_view", pf)
    pf.UpdatePipeline()

    def _names(s):
        try:
            n = list(s.CellData.keys())
        except Exception:
            n = []
        if n:
            return n
        try:
            s.UpdatePipeline()
            cdi = s.GetDataInformation().GetCellDataInformation()
            return [cdi.GetArrayInformation(i).GetName()
                    for i in range(cdi.GetNumberOfArrays())]
        except Exception:
            return []

    def _thr(s, array, lo, hi, name):
        if array not in _names(s):
            return None
        try:
            t = Threshold(Input=s)
            t.Scalars = ("CELLS", array)
            try:
                t.LowerThreshold = float(lo)
                t.UpperThreshold = float(hi)
                t.ThresholdMethod = "Between"
            except Exception:
                t.ThresholdRange = [float(lo), float(hi)]
            RenameSource(name, t)
            t.UpdatePipeline()
            if int(t.GetDataInformation().GetNumberOfCells()) <= 0:
                Delete(t)
                return None
            return t
        except Exception as e:
            print("Eps1_View: threshold %s skipped: %s" % (name, e))
            return None

    main = _thr(pf, "STRUCTURAL", 1, 1, "structural") or pf
    if main is not pf:
        print("Eps1_View: rigid-body link lines dropped.")
    act = _thr(main, "EROSION_STATUS", 0.5, 1.0, "active_elements")
    if act is not None:
        main = act
        print("Eps1_View: eroded elements hidden (EROSION_STATUS >= 0.5 kept).")

    disp = Show(main, view)
    if not hasattr(disp, "SMProxy"):   # PV 6.1 GUI: Show can return a wrapper
        try:                           # function - fetch the real rep proxy
            disp = GetRepresentation(main, view)
        except Exception:
            pass
    for s in (src, pf):
        if s is not main:
            try:
                Hide(s, view)
            except Exception:
                pass

    names = _names(main)
    field = None
    for cand in ("eps1_solid", "eps1_membrane"):
        if cand in names:
            field = cand
            break
    if field is None:
        others = sorted(n for n in names if n.startswith("eps1_"))
        field = others[0] if others else None
    if field is None:
        for n in names:
            u = n.upper()
            if "PLASTIC" in u and "STRAIN" in u and "RATE" not in u:
                field = n
                break
    try:
        # Dark edge colour so 'Surface With Edges' shows the mesh as faint
        # lines over the colour field instead of covering it.
        disp.EdgeColor = [0.15, 0.15, 0.18]
    except Exception:
        pass

    def _style_lut(lut, lo, hi):
        # Light grey at zero, colour arriving within a few percent of the
        # range, red pinned at the top; above-range renders magenta.
        d = float(hi) - float(lo)
        if d <= 0:
            return
        pts = []
        for f, rgb in ((0.00, (0.87, 0.87, 0.89)),
                       (0.04, (0.62, 0.76, 0.98)),
                       (0.12, (0.20, 0.50, 0.95)),
                       (0.30, (0.10, 0.75, 0.45)),
                       (0.55, (0.95, 0.85, 0.10)),
                       (0.78, (0.95, 0.55, 0.10)),
                       (1.00, (0.80, 0.05, 0.05))):
            pts += [float(lo) + f * d, rgb[0], rgb[1], rgb[2]]
        lut.RGBPoints = pts
        try:
            lut.ColorSpace = "Lab"
            lut.UseAboveRangeColor = 1
            lut.AboveRangeColor = [1.0, 0.0, 1.0]
        except Exception:
            pass

    if field:
        ColorBy(disp, ("CELLS", field))
        vmax = 0.0
        try:
            vmax = float(main.CellData[field].GetRange(0)[1])
        except Exception:
            pass
        _lut_hi = vmax if vmax > 0.0 else 0.02
        lut = GetColorTransferFunction(field)
        lut.RescaleTransferFunction(0.0, _lut_hi)
        _style_lut(lut, 0.0, _lut_hi)
        try:
            lut.AutomaticRescaleRangeMode = "Never"
        except Exception:
            pass
        disp.SetScalarBarVisibility(view, True)
        try:
            sb = GetScalarBar(lut, view)
            sb.Title = field
            sb.ComponentTitle = ""
        except Exception:
            pass
        print("Eps1_View: colouring by %s (LUT 0-%g)."
              % (field, vmax if vmax > 0.0 else 0.02))

        # Hot-spot rings: red boundary rings around cells at or above 50% of
        # the frame max (the macro has no deck manifest, so the frame max is
        # the only available reference).
        hot = _thr(main, field, 0.5 * _lut_hi, 1e9, "hot_spots")
        if hot is not None:
            try:
                Hide(hot, view)
                ring = FeatureEdges(Input=ExtractSurface(Input=hot))
                ring.BoundaryEdges = 1
                ring.FeatureEdges = 0
                ring.ManifoldEdges = 0
                ring.NonManifoldEdges = 0
                RenameSource("hot_spot_rings", ring)
                rd = Show(ring, view)
                if not hasattr(rd, "SMProxy"):
                    rd = GetRepresentation(ring, view)
                for clear in (lambda: ColorBy(rd, ("CELLS", None)),
                              lambda: ColorBy(rd, None)):
                    try:
                        clear()
                        break
                    except Exception:
                        continue
                rd.DiffuseColor = rd.AmbientColor = [1.0, 0.1, 0.1]
                try:
                    rd.LineWidth = 3.0
                except Exception:
                    pass
                print("Eps1_View: red rings around cells with %s >= %g (50%% of frame max)."
                      % (field, 0.5 * _lut_hi))
            except Exception as e:
                print("Eps1_View: hot-spot rings skipped: %s" % e)

        # Live max readout, lower-left corner, follows the time slider.
        try:
            ann_max = PythonAnnotation(Input=main)
            ann_max.ArrayAssociation = "Cell Data"
            ann_max.Expression = ("'max %s = %%.4g' %% input.CellData['%s'].max()"
                                  % (field, field))
            RenameSource("max_readout", ann_max)
            ad_max = Show(ann_max, view)
            if not hasattr(ad_max, "SMProxy"):
                ad_max = GetRepresentation(ann_max, view)
            try:
                ad_max.WindowLocation = "Lower Left Corner"
                ad_max.Bold = 1
            except Exception:
                pass
        except Exception as e:
            print("Eps1_View: max readout skipped: %s" % e)
    else:
        print("Eps1_View: no eps1 or plastic-strain field produced - see the "
              "'eps1 filter' message above for the reason (geometry is still shown). "
              "Cell arrays: %s" % (", ".join(names) or "none"))
    Render()
'''

__all__ = [n for n in dir() if not n.startswith('__')]

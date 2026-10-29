"""Checked face and edge merging for build123d.

build123d merges the coplanar faces and collinear edges of every Boolean result and of Shape.clean() with
ShapeUpgrade_UnifySameDomain (faces and edges together). On some solids the merge returns an invalid solid from a
valid one: two half-ring faces of a fillet around a circular edge that share one torus are merged into one face
over the same half, and every later Boolean on the part fails or removes the wrong volume. install() replaces the
ShapeUpgrade_UnifySameDomain used by build123d with CheckedUnify: when the merged shape is invalid and the input
was valid, the faces only, then the edges only are merged, and otherwise nothing is merged.
"""

from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain as _Unify

# above this number of faces the result is not checked (STL mesh bodies)
MAX_CHECK_FACES = 5000
# count of merges that were replaced (for the tests and the log)
FALLBACKS = {"count": 0}


def _valid(shape):
    from OCP.BRepCheck import BRepCheck_Analyzer
    try:
        try:
            return BRepCheck_Analyzer(shape, True, True).IsValid()     # the sub-shapes checked in parallel
        except TypeError:
            return BRepCheck_Analyzer(shape).IsValid()
    except Exception:
        return False


def _n_faces(shape):
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    n = 0
    while ex.More() and n <= MAX_CHECK_FACES:
        n += 1
        ex.Next()
    return n


class CheckedUnify:
    """ShapeUpgrade_UnifySameDomain with a validity check of the result (same calls as the OCCT class)."""

    def __init__(self, shape=None, unify_edges=True, unify_faces=True, concat_bsplines=False):
        self._args = (shape, unify_edges, unify_faces, concat_bsplines)
        self._calls = []
        self._real = _Unify(shape, unify_edges, unify_faces, concat_bsplines) if shape is not None else _Unify()

    def __getattr__(self, name):
        attr = getattr(self._real, name)
        if callable(attr) and name not in ("Shape", "History", "Build"):
            def call(*a, **k):
                self._calls.append((name, a, k))
                return attr(*a, **k)
            return call
        return attr

    def Build(self):
        self._real.Build()
        shape, ue, uf, cb = self._args
        if shape is None or not (ue and uf) or _n_faces(shape) > MAX_CHECK_FACES:
            return
        if _valid(self._real.Shape()) or not _valid(shape):
            return
        for e, f in ((False, True), (True, False), (False, False)):
            alt = _Unify(shape, e, f, cb)
            for name, a, k in self._calls:
                try:
                    getattr(alt, name)(*a, **k)
                except Exception:
                    pass
            alt.Build()
            if _valid(alt.Shape()):
                self._real = alt
                FALLBACKS["count"] += 1
                return

    def Shape(self):
        return self._real.Shape()

    def History(self):
        return self._real.History()


def install():
    """Replaces the merge class in the build123d modules that use it (idempotent)."""
    import importlib
    for mod in ("build123d.topology.shape_core", "build123d.topology", "build123d.topology.history"):
        try:
            m = importlib.import_module(mod)
        except ImportError:
            continue
        if getattr(m, "ShapeUpgrade_UnifySameDomain", None) is _Unify:
            m.ShapeUpgrade_UnifySameDomain = CheckedUnify

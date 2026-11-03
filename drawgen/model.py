# -*- coding: utf-8 -*-
"""STEP loading and part list."""
import os

from OCP.BRep import BRep_Builder
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopoDS import TopoDS_Compound

from .project import bounding_box, _static

_volume_props = _static(BRepGProp, "VolumeProperties")


class Part(object):
    def __init__(self, pid, name, shape):
        self.id = pid
        self.name = name
        self.shape = shape          # TopoDS_Shape
        bb = bounding_box(shape)
        self.bbox = bb
        props = GProp_GProps()
        _volume_props(shape, props)
        self.volume = props.Mass()  # mm^3

    def info(self):
        x0, y0, z0, x1, y1, z1 = self.bbox
        return {"id": self.id, "name": self.name,
                "size_mm": [round(x1 - x0, 3), round(y1 - y0, 3), round(z1 - z0, 3)],
                "volume_mm3": round(self.volume, 1)}


def load_step(path):
    """Read a STEP file. Returns a list of Part, one per solid, named from the STEP labels."""
    return [Part(i, name, shape) for i, (name, shape) in enumerate(named_solids(path))]


def named_solids(path):
    """Read a STEP file. Returns [(name, TopoDS solid)], one per solid, named from the STEP labels (without the
    bounding box and volume of Part)."""
    return _read_named(path)[0]


def _read_named(path):
    """([(name, TopoDS solid)], [(name, TopoDS faces)]) of a STEP file: the solids named from the STEP labels, and
    per STEP component without solids its faces (one shell, or a compound of the faces), named from its label."""
    from build123d import import_step
    comp = import_step(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    parts, surfs = [], []
    names, snames = {}, {}

    def add(name, shape, lst=parts, used=names):
        name = name or stem
        n = used.get(name, 0)
        used[name] = n + 1
        if n:
            name = "%s_%d" % (name, n + 1)
        lst.append((name, shape))

    def walk(obj, inherited):
        label = getattr(obj, "label", "") or inherited
        children = list(getattr(obj, "children", None) or [])
        if children:
            for ch in children:
                walk(ch, label)
            return
        solids = obj.solids() if hasattr(obj, "solids") else []
        if len(solids) == 1:
            add(label, solids[0].wrapped)
        elif solids:
            for i, s in enumerate(solids):
                add("%s_%d" % (label, i + 1) if label else "", s.wrapped)
        else:
            faces = obj.faces() if hasattr(obj, "faces") else []
            if faces:
                shells = obj.shells()
                if len(shells) == 1 and len(shells[0].faces()) == len(faces):
                    add(label, shells[0].wrapped, surfs, snames)
                else:
                    add(label, compound([f.wrapped for f in faces], always=True), surfs, snames)

    walk(comp, "")
    if not parts and not surfs:
        for s in comp.solids():
            add("", s.wrapped)
    return parts, surfs


_STEP_SOLIDS = {}   # (path, mtime, size) -> (compound, [(name, solid)], [(name, faces)])


def _step_read(path):
    st = os.stat(path)
    key = (os.path.normcase(os.path.abspath(path)), st.st_mtime, st.st_size)
    if key not in _STEP_SOLIDS:
        for k in [k for k in _STEP_SOLIDS if k[0] == key[0]]:
            _STEP_SOLIDS.pop(k, None)
        while len(_STEP_SOLIDS) >= 8:
            _STEP_SOLIDS.pop(next(iter(_STEP_SOLIDS)))
        named, surfs = _read_named(path)
        _STEP_SOLIDS[key] = (compound([sh for _, sh in named]) if named else None, named, surfs)
    return _STEP_SOLIDS[key]


def step_solids(path):
    """Solids of a STEP file as (name, build123d Shape), indexed and named as load_step lists them, and the compound
    of all solids. The file is read once per path, modification time and size; used by the assembly components and
    the Import geometry feature of parts, so a solid index means the same solid everywhere."""
    from build123d import Shape
    comp, named, _s = _step_read(path)
    # new build123d wrappers on every call: callers may set labels or parents on them
    return (Shape.cast(comp) if comp is not None else None), [(n, Shape.cast(s)) for n, s in named]


def step_surfaces(path):
    """Faces of the STEP components without solids: [(name, build123d Shape)] (a shell, or a compound of faces)."""
    from build123d import Shape
    return [(n, Shape.cast(s)) for n, s in _step_read(path)[2]]


def compound(shapes, always=False):
    """TopoDS compound of the shapes (one shape alone is returned as it is unless always)."""
    if len(shapes) == 1 and not always:
        return shapes[0]
    b = BRep_Builder()
    c = TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c

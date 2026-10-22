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
    from build123d import import_step
    comp = import_step(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    parts = []
    names = {}

    def add(name, shape):
        name = name or stem
        n = names.get(name, 0)
        names[name] = n + 1
        if n:
            name = "%s_%d" % (name, n + 1)
        parts.append((name, shape))

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
        else:
            for i, s in enumerate(solids):
                add("%s_%d" % (label, i + 1) if label else "", s.wrapped)

    walk(comp, "")
    if not parts:
        for s in comp.solids():
            add("", s.wrapped)
    return parts


_STEP_SOLIDS = {}   # (path, mtime, size) -> (compound, [(name, solid)])


def step_solids(path):
    """Solids of a STEP file as (name, build123d Shape), indexed and named as load_step lists them, and the compound
    of all solids. The file is read once per path, modification time and size; used by the assembly components and
    the Import STEP feature of parts, so a solid index means the same solid everywhere."""
    from build123d import Shape
    st = os.stat(path)
    key = (os.path.normcase(os.path.abspath(path)), st.st_mtime, st.st_size)
    if key not in _STEP_SOLIDS:
        for k in [k for k in _STEP_SOLIDS if k[0] == key[0]]:
            _STEP_SOLIDS.pop(k, None)
        while len(_STEP_SOLIDS) >= 8:
            _STEP_SOLIDS.pop(next(iter(_STEP_SOLIDS)))
        named = named_solids(path)
        _STEP_SOLIDS[key] = (compound([sh for _, sh in named]) if named else None, named)
    comp, named = _STEP_SOLIDS[key]
    # new build123d wrappers on every call: callers may set labels or parents on them
    return (Shape.cast(comp) if comp is not None else None), [(n, Shape.cast(s)) for n, s in named]


def compound(shapes):
    if len(shapes) == 1:
        return shapes[0]
    b = BRep_Builder()
    c = TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c

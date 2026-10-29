"""SHINYCAD program package (server, drawings, parts, assemblies, analysis)."""

try:                                   # checked face and edge merging in build123d (occfix.py)
    from . import occfix as _occfix
    _occfix.install()
except ImportError:                    # build123d / OCP not installed: nothing to patch
    pass

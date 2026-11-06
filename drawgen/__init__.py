"""SHINYCAD program package (server, drawings, parts, assemblies, analysis)."""

try:                                   # checked face and edge merging in build123d (occfix.py)
    from . import occfix as _occfix
    _occfix.install()
except ImportError:                    # build123d / OCP not installed: nothing to patch
    pass

try:
    # Boolean operations run their face intersections on all processor cores. The flag is the default of every
    # BOPAlgo algorithm created afterwards, including those inside the offset, thicken, split and fillet operations
    # of OpenCascade that do not take a SetRunParallel call of their own.
    from OCP.BOPAlgo import BOPAlgo_Options as _BOPAlgo_Options
    _BOPAlgo_Options.SetParallelMode_s(True)
except ImportError:
    pass

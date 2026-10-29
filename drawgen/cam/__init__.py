# -*- coding: utf-8 -*-
"""CAM: toolpaths for a 3-axis milling machine from a part of the Part tab (job.py: the job document and the
run; tools.py: tool bits; geom.py: regions, sections and height maps; ops2d.py, adaptive.py, vcarve.py,
ops3d.py: the operations; placement.py: the model placement; feeds.py: feeds and speeds; dressup.py: path dressups, copy and array; post.py: G-code)."""
from . import tools, geom, job, post, placement, feeds
from .tools import DEFAULT_TOOLS, SHAPES, SHAPE_NAMES, tool_profile, tool_solid, sweep_line, normalize as normalize_tool, check as check_tool
from .geom import bbox as _bbox, face_kinds, volume as _volume, common_volume as _common_volume
from .job import (migrate, run, remaining, stock_solid, origin_of, heights, levels, sanity, template, apply_template,
                  controller_defaults, cache_clear, OP_NAMES, SUPPLEMENTAL, DERIVED, DEFAULT_SETUP, _f)
from .post import POSTS, gcode
from .ops2d import undercut_faces, undercut_info, undercut_fill, undercut_passes

__all__ = ["tools", "geom", "job", "post", "placement", "feeds", "DEFAULT_TOOLS", "SHAPES", "SHAPE_NAMES", "tool_profile", "tool_solid", "sweep_line",
           "normalize_tool", "check_tool", "_bbox", "face_kinds", "_volume", "_common_volume", "migrate", "run", "remaining",
           "stock_solid", "origin_of", "heights", "levels", "sanity", "template", "apply_template", "controller_defaults",
           "cache_clear", "OP_NAMES", "SUPPLEMENTAL", "DERIVED", "DEFAULT_SETUP", "_f", "POSTS", "gcode", "undercut_faces",
           "undercut_info", "undercut_fill", "undercut_passes"]

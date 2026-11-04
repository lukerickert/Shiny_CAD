"""Analysis types of the explicit analysis (ORC**3 workspace_modes.py).

Which sections of the Build panel each type shows. Hidden fields keep their values and still act at build time;
the Build panel names a hidden field that is active.

Section keys:
    floor        rigid floor (test mode + Floor Z)
    velocity     the impactor velocity / load-hold-unload driver
    rigidify     the Rigidify part(s) field
    target_rp    the Target RP field
    point_mass   the concentrated mass field
    ties         the ties
    advanced     the advanced options
    rivet        the Rivet section (gauge rings, force vs relative displacement)
"""

from .constants import RBV_EXPL, RBV_PROFILE, RBV_PROFILE_F, RBV_NONE

MODE_IMPACT = "Impact / drop test"
MODE_QS     = "Quasi-static (load-hold-unload)"
MODE_RIVET  = "Rivet coupon calibration"
MODE_ALL    = "Advanced (all features)"

ANALYSIS_MODES = (MODE_IMPACT, MODE_QS, MODE_RIVET, MODE_ALL)

MODE_HELP = {
    MODE_IMPACT: ("Velocity-driven impact: the model /RBODY (or a rigidified part) gets an "
                  "/INIVEL. Optional infinite rigid floor for drop tests. The concentrated mass "
                  "field supplies the impactor mass and inertia."),
    MODE_QS:     ("Load-hold-unload indentation/press: the /RBODY main node is driven by a "
                  "smooth /IMPDISP displacement profile or a /CLOAD force profile. "
                  "Floor, rigidify and concentrated mass are hidden."),
    MODE_RIVET:  ("Lap-joint coupon calibration: the grip RP is driven (Target RP selects the /RBODY when there are "
                  "several); gauge rings and force vs relative displacement in the Rivet section."),
    MODE_ALL:    ("All fields shown."),
}

# What each mode HIDES. Everything not listed stays visible.
MODE_SPEC = {
    MODE_IMPACT: {
        "hide_sections": {"target_rp", "advanced", "rivet"},
        "rbv_values":    (RBV_EXPL, RBV_NONE),
    },
    MODE_QS: {
        "hide_sections": {"floor", "rigidify", "point_mass", "advanced", "rivet"},
        "rbv_values":    (RBV_PROFILE, RBV_PROFILE_F, RBV_NONE),
    },
    MODE_RIVET: {
        "hide_sections": {"floor", "rigidify", "point_mass", "advanced"},
        "rbv_values":    None,
    },
    MODE_ALL: {
        "hide_sections": set(),
        "rbv_values":    None,
    },
}

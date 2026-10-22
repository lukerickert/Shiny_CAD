"""Constants of the explicit analysis (ORC**3 core): the material library, the tie, contact, impactor
velocity and failure modes with their help texts, and the engine output parsing.
Taken from ORC**3 workspace_constants.py; the GUI theme, the config file and the Tools list are not used here.
"""

import os
import re

# ==============================================================================
# PREDEFINED MATERIAL LIBRARY
# ==============================================================================
MATERIAL_LIBRARY = {
    "None (Use PrePoMax Data)": None,
    
    "Steel S355 (DNVGL 19-Point Standard)": {
        "rho": 7.85e-9, "E": 210000.0, "nu": 0.3,
        "curve": [
            (0.0000, 355.00), (0.0150, 355.00), (0.0200, 368.12), (0.0300, 389.96),
            (0.0400, 408.08), (0.0500, 423.82), (0.0600, 437.88), (0.0800, 462.59),
            (0.1000, 483.94), (0.1200, 502.88), (0.1500, 528.18), (0.2000, 564.44),
            (0.2500, 595.03), (0.3000, 621.72), (0.4000, 667.92), (0.5000, 707.39),
            (0.6000, 741.98), (0.8000, 802.26), (1.0000, 853.86)
        ]
    },

    # v20.63: same DNVGL 19-point curve, plus Cowper-Symonds rate scaling.
    # The build writes 5 hardening curves: the static base plus the base
    # scaled by DIF = 1 + (rate/D)^(1/q) at each rate in "rates". D/q here are
    # an S355-specific literature fit (Structures Under Shock & Impact VIII:
    # D=5000 1/s, q=2.5); the classic mild-steel 40.4/5 pair roughly doubles
    # the yield already at 100/s and is NOT appropriate for this grade.
    "Steel S355 (DNVGL 19-pt + Cowper-Symonds rate)": {
        "law": "LAW36",
        "rho": 7.85e-9, "E": 210000.0, "nu": 0.3,
        "cs_D": 5000.0, "cs_q": 2.5,
        "rates": [1.0, 10.0, 100.0, 1000.0],   # static base curve is added automatically
        "curve": [
            (0.0000, 355.00), (0.0150, 355.00), (0.0200, 368.12), (0.0300, 389.96),
            (0.0400, 408.08), (0.0500, 423.82), (0.0600, 437.88), (0.0800, 462.59),
            (0.1000, 483.94), (0.1200, 502.88), (0.1500, 528.18), (0.2000, 564.44),
            (0.2500, 595.03), (0.3000, 621.72), (0.4000, 667.92), (0.5000, 707.39),
            (0.6000, 741.98), (0.8000, 802.26), (1.0000, 853.86)
        ]
    },

    # v20.63: analytic Johnson-Cook (LAW2). a/b/n are a least-squares fit of
    # the DNVGL C208 19-point S355 curve (within +-3% for eps_p > 5%; the
    # power law cannot reproduce the Lueders plateau, so it overshoots ~11%
    # at 1.5% strain - fine for rate demos, use the LAW36 entries for C208
    # deliverables). C=0.01 with eps0=1.0 /s is a deliberately mild default:
    # sweep C (0 .. ~0.04) to demonstrate/calibrate rate dependence.
    "Steel S355 (Johnson-Cook fit of DNVGL curve)": {
        "law": "LAW2",
        "rho": 7.85e-9, "E": 210000.0, "nu": 0.3,
        "a": 355.0, "b": 523.2, "n": 0.617,
        "c": 0.01, "eps0": 1.0
    },

    # v20.63: 6061-T6 is the everyday general-purpose aluminium; these are
    # the standard literature Johnson-Cook constants (Lesuer et al., LLNL
    # "Modeling Large-Strain, High-Rate Deformation in Metals" - the set
    # everyone reproduces). Rate sensitivity of 6061-T6 is genuinely tiny
    # (C=0.002). For EU 6082-T6 these are a fair first approximation
    # (similar strength class) but not a substitute for a proper fit.
    "Aluminium 6061-T6 (Johnson-Cook)": {
        "law": "LAW2",
        "rho": 2.70e-9, "E": 68900.0, "nu": 0.33,
        "a": 324.1, "b": 113.8, "n": 0.42,
        "c": 0.002, "eps0": 1.0
    },

    # v20.63: purely elastic (LAW1) - for indenters, tooling, supports.
    # Never receives a /FAIL card regardless of the Failure selection.
    "Elastic Tool Steel (LAW1, no yield)": {
        "law": "LAW1",
        "rho": 7.85e-9, "E": 210000.0, "nu": 0.3
    },
    "Elastic Tungsten Carbide (LAW1, no yield)": {
        "law": "LAW1",
        "rho": 1.50e-8, "E": 600000.0, "nu": 0.22
    },
    
    "Steel S355 (Extended High-Strain)": {
        "rho": 7.85e-9, "E": 210000.0, "nu": 0.28,
        "curve": [
            (0.0, 237.0), (2.619e-04, 244.0), (7.859e-04, 256.0), (0.00157, 269.0), 
            (0.00262, 282.0), (0.00393, 294.0), (0.0055, 306.0), (0.00733, 317.0), 
            (0.00943, 327.0), (0.0118, 337.0), (0.0144, 346.0), (0.0173, 355.0), 
            (0.0204, 363.0), (0.0238, 371.0), (0.0275, 378.0), (0.0314, 385.0), 
            (0.0356, 392.0), (0.0401, 399.0), (0.0448, 405.0), (0.0498, 411.0), 
            (0.055, 417.0), (0.0605, 422.0), (0.0663, 428.0), (0.0723, 433.0), 
            (0.0786, 439.0), (0.0851, 444.0), (0.0919, 448.0), (0.099, 453.0), 
            (0.106, 458.0), (0.114, 462.0), (0.122, 467.0), (0.13, 471.0), 
            (0.138, 476.0), (0.147, 480.0), (0.156, 484.0), (0.165, 488.0), 
            (0.174, 492.0), (0.184, 496.0), (0.194, 499.0), (0.204, 503.0), 
            (0.215, 507.0), (0.226, 510.0), (0.237, 514.0), (0.248, 517.0), 
            (0.259, 521.0), (0.271, 524.0), (0.283, 527.0), (0.295, 531.0), 
            (0.308, 534.0), (0.321, 537.0), (0.334, 540.0), (0.347, 543.0), 
            (0.361, 546.0), (0.375, 549.0), (0.389, 552.0), (0.403, 555.0), 
            (0.418, 558.0), (0.433, 561.0), (0.448, 563.0), (0.464, 566.0), 
            (0.479, 569.0), (0.495, 572.0), (0.512, 574.0), (0.528, 577.0), 
            (0.545, 580.0), (0.562, 582.0), (0.579, 585.0), (0.597, 587.0), 
            (0.614, 590.0), (0.633, 592.0), (0.651, 595.0), (0.669, 597.0), 
            (0.688, 600.0), (0.707, 602.0), (0.727, 604.0), (0.746, 607.0), 
            (0.766, 609.0), (0.787, 611.0), (0.807, 613.0), (0.828, 616.0), 
            (0.849, 618.0), (0.87, 620.0), (0.891, 622.0), (0.913, 625.0), 
            (0.935, 627.0), (0.957, 629.0), (0.98, 631.0), (1.0, 633.0), 
            (1.03, 635.0), (1.05, 637.0), (1.07, 639.0), (1.1, 641.0), 
            (1.12, 643.0), (1.14, 645.0), (1.17, 647.0), (1.19, 649.0), 
            (1.22, 651.0), (1.24, 653.0), (1.27, 655.0), (1.3, 657.0), 
            (1.31, 658.0)
        ]
    },

    # v20.70: RMS Titanic hull plate steel, from Foecke NISTIR 6118 (1998).
    # Tensile: YS 38-41 ksi (262-280 MPa), UTS 62.5 ksi (430 MPa), ~29-30%
    # elong at room temp; chemistry ~ AISI 1018. This is the ROOM-TEMPERATURE
    # flow curve (a/b/n -> UTS 432 MPa at eps_p~0.25). The -2 C ice-water
    # brittleness (Charpy DBTT +40 C long / +70 C trans, <5% ductile fracture
    # at service temp) is NOT in the flow curve - apply it via the Failure
    # section with a low failure strain when you want the plate brittle (hull
    # ROI). Keep failure generous in the calibration coupon so rivets govern.
    "Steel - Titanic hull plate (NIST/Foecke, room-temp flow)": {
        "law": "LAW2",
        "rho": 7.85e-9, "E": 210000.0, "nu": 0.3,
        "a": 262.0, "b": 340.0, "n": 0.50
    },

    # v20.70: Titanic hull-RIVET wrought iron, TRANSVERSE + cold-degraded.
    # Wrought iron with 9.3% slag (NISTIR 6118; >3x normal). Strongly
    # anisotropic: transverse tensile strength ~0.5-0.65x the longitudinal
    # (~350 MPa, "strong mild steel"), transverse strain-to-failure ~10x lower
    # - the plane the rivets actually popped on (slag stringers normal to the
    # tensile axis at the driven head). Flow curve is the transverse-degraded
    # envelope (yield ~150, ~200 MPa at small strain); with a von-Mises solid
    # the emergent single-shear capacity is ~55-70 kN per 25.4 mm rivet.
    # Brittleness is the POINT: pair with the Failure section at a LOW failure
    # strain (~0.02) so it pops abruptly. E ~190 GPa (wrought iron). No rate
    # term - calibrate quasi-static first.
    "Wrought iron - Titanic rivet (transverse, cold-degraded)": {
        "law": "LAW2",
        "rho": 7.85e-9, "E": 190000.0, "nu": 0.3,
        "a": 150.0, "b": 250.0, "n": 0.45
    }
}

# ==============================================================================
# CONFIGURATION PERSISTENCE
# ==============================================================================
# ------------------------------------------------------------------ identity
# One definition of what this program is called. The window title, the console
# banner, the per-build settings report and the docs all read these; before
# v21.8 each carried its own literal and the version had drifted five releases
# out of date (report said v20.67, title said v21.7 MK2).
#
# ORC**3 is written the Fortran way - "ORC cubed" - for the three C's:
# CalculiX, Converter, Control. Pure ASCII, so it types on any keyboard and
# survives any encoding.
#
# WORKSPACE_NAME_FILE is not a nicety: an asterisk is illegal in a Windows
# path, so anything that becomes a filename or an identifier must use it.
WORKSPACE_NAME       = "ORC**3"
WORKSPACE_NAME_FILE  = "ORC3"
WORKSPACE_TAGLINE    = "OpenRadioss CalculiX Converter and Control"
WORKSPACE_VERSION    = "v1.0"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))   # inp2rad.py, inp_to_linear.py, inertia_calc.py

# ==============================================================================
# TIE MODES
# ==============================================================================
# Exactly one mechanism produces tie interfaces per build - no silent fallback
# between them. The help text is shown live in the GUI so the behaviour is
# self-documenting when you come back to a model months later.
TIE_AUTO   = "Auto (*TIE from INP)"
TIE_SCOPED = "Scoped pairs (box below)"
TIE_GLOBAL = "Single global tie"
TIE_NONE   = "None"
TIE_MODES  = (TIE_AUTO, TIE_SCOPED, TIE_GLOBAL, TIE_NONE)
TIE_HELP = {
    TIE_AUTO:   ("Ties are read from the *TIE cards in the source .inp - define them visually in "
                 "PrePoMax (Find Contact Pairs or Selection). Each *TIE's Position tolerance is its "
                 "search distance; 'Fallback dist' below covers ties exported without one. "
                 "If the .inp has no *TIE, the build warns and writes NO ties."),
    TIE_SCOPED: ("Ties come ONLY from the box below, one per line:  secondary > master : distance  "
                 "(parts by name substring or PID). Use when each joint needs its own search "
                 "distance and PrePoMax ties aren't defined. Empty box = warning, NO ties."),
    TIE_GLOBAL: ("ONE universal /INTER/TYPE2: any node may bond to any nearby surface within "
                 "'Tie dist'. Blunt but quick - fine for simple stacks, risky when unrelated "
                 "parts pass within the distance. Distance 0 = warning, NO tie."),
    TIE_NONE:   ("No tie interfaces are written. Parts interact only through contact "
                 "(and any rigid bodies / walls)."),
}

# ==============================================================================
# GENERAL CONTACT MODES (v20.63)
# ==============================================================================
# Replaces the old Self Contact on/off checkbox with an explicit choice of
# interface formulation, same philosophy as Tie/Velocity modes. All modes use
# the universal groups the build always writes (GRNOD 9999998 = all nodes,
# SURF 9999999 = external surface of all parts). Card layouts verified against
# the OpenRadioss hm_cfg_files starter readers (radioss2021/2023 formats).
CONTACT_T7   = "TYPE7 (node-to-surface)"
CONTACT_T19  = "TYPE19 (TYPE7 + edge-to-edge)"
CONTACT_T24  = "TYPE24 (constant stiffness)"
CONTACT_NONE = "None"
CONTACT_MODES = (CONTACT_T7, CONTACT_T19, CONTACT_T24, CONTACT_NONE)
CONTACT_HELP = {
    CONTACT_T7:  ("The legacy card, unchanged: one universal /INTER/TYPE7 (all nodes vs all "
                  "external surfaces, Istf=4, Igap=2, Inacti=6). Robust default for "
                  "plate-dominated impact. Blind spot: shell EDGES sliding past each other "
                  "(perpendicular plate edges, unstiffened rims) can pass through - node-to-"
                  "surface only. Nonlinear stiffness can bite the timestep under deep "
                  "penetration."),
    CONTACT_T19: ("One /INTER/TYPE19: internally two symmetric TYPE7s plus a TYPE11 edge-to-"
                  "edge interface generated automatically from the same universal surface "
                  "(single-surface form: surf_IDs=9999999, surf_IDm=0). Fixes the TYPE7 "
                  "edge blind spot for free deck and girder edges and impactor corners. Costs more "
                  "than TYPE7; Iedge=1 (external shell edges only) keeps it reasonable."),
    CONTACT_T24: ("One /INTER/TYPE24 single-surface contact (surf_ID1=9999999) with Iedge=1 "
                  "shell-edge contact. CONSTANT penalty stiffness: the timestep is never "
                  "cut by contact penetration - attractive for heavily loaded decks. Solids "
                  "get a physical zero gap; initial penetrations are tracked, not fought. "
                  "Idel=2 drops failed segments from the contact. Behaviour differs subtly "
                  "from TYPE7 (gapless solids, constant K), so don't hot-swap mid-study."),
    CONTACT_NONE: ("No general contact is written. Parts interact only through ties, the "
                   "model's own interfaces, rigid bodies and walls. Anything else passes "
                   "through everything."),
}

# ==============================================================================
# RIGID BODY MODES
# ==============================================================================
# Same philosophy as Tie Mode: one explicit choice, no silent fallback, and a
# live help line so the behaviour is self-documenting. The velocity source is
# its own explicit choice because a rigid body moves ONLY via its main node -
# getting this wrong is the classic "impactor doesn't move" failure.
# v20.59: Rigidify-part injection removed. The model owns the impactor /RBODY
# (PrePoMax: reference point at the CoG + rigid body tie + point mass); the
# build only DRIVES it by writing /INIVEL/TRA onto that body's MAIN node.
RBV_EXPL  = "Explicit (Vx Vy Vz below)"
RBV_PROFILE = "Load-hold-unload (imposed disp)"
RBV_PROFILE_F = "Load-hold-unload (force /CLOAD)"
RBV_NONE  = "None (deck as-is)"
RBV_MODES = (RBV_EXPL, RBV_PROFILE, RBV_PROFILE_F, RBV_NONE)
RBV_HELP = {
    RBV_EXPL: ("Velocity: the Vx Vy Vz field is written as /INIVEL/TRA on the MAIN node of "
               "the model's single /RBODY (the PrePoMax reference point). Requires EXACTLY "
               "ONE /RBODY in the deck: zero = define the rigid body in PrePoMax (RP at the "
               "CoG + rigid body tie), several = ambiguous target; either way a RIGID "
               "WARNING is logged and NO velocity is written. A value that fails to parse = "
               "warning and NO velocity."),
    RBV_PROFILE: ("Drives the /RBODY main node with a smooth load-hold-unload displacement "
                  "profile (for Rockwell-style push/hold/retract): builds a /FUNCT (0->1->0 "
                  "quintic-eased trapezoid from the Peak/Ramp/Hold/Settle fields) and an "
                  "/IMPDISP on the main node in the chosen direction, scaled by Peak disp. "
                  "The four times are in seconds; smaller total = faster = higher strain "
                  "rate, so a rate sweep is just several builds with scaled times. Same "
                  "single-/RBODY requirement and warnings as Explicit. If the run Tstop "
                  "exceeds the profile, a trailing zero point holds the indenter retracted "
                  "through the settle; if Tstop is shorter, the profile is truncated and a "
                  "WARNING is logged."),
    RBV_NONE: ("Velocity: nothing is written - the deck keeps exactly the kinematics the "
               "model defines. The build still logs the deck's /RBODY and /INIVEL counts."),
    RBV_PROFILE_F: ("Force control: same smooth load-hold-unload SHAPE as the imposed-disp mode, "
                    "but written as a /CLOAD on the /RBODY main node scaled by 'Peak disp' - "
                    "here that field is the PEAK FORCE (deck force units; for a quarter model "
                    "use a quarter of the real load, e.g. ~368 N for the 150 kgf HRC major "
                    "load, and sign it negative to push in -Z). More physical for hardness "
                    "(you command the load, the penetration is the result), but with no "
                    "kinematic constraint the indenter can overshoot if the ramp is too steep - "
                    "keep ramps gentle and watch KE/IE. Same single-/RBODY rule, Tstop fitting "
                    "and warnings as the imposed-disp mode."),
}
# Easings for the load-hold-unload profile (shared with the standalone
# amplitude_gen tool). Smootherstep (quintic) has zero slope AND curvature at
# both ramp ends - no jerk, the Abaqus SMOOTH STEP idea.
LHU_EASINGS = ("Smootherstep", "Smoothstep", "Cosine", "Linear")

# ==============================================================================
# FAILURE MODELS
# ==============================================================================
FAIL_EPS  = "Equivalent plastic strain"
FAIL_JC   = "Johnson-Cook (triaxiality)"
FAIL_TENS = "Max principal strain"
FAIL_HELP = {
    FAIL_EPS:  ("'Plastic fail strain' is written into EVERY material: Eps_max on LAW2/"
                "PLAS_JOHNS and Eps_p_max/Eps_t/Eps_m on LAW36/PLAS_TAB, library-replaced "
                "and kept-from-model alike. Empty or 0 = NO element failure anywhere."),
    FAIL_JC:   ("A /FAIL/JOHNSON card (triaxiality-dependent: D1-D5, e0, Ifail_sh) is added "
                "to LIBRARY-REPLACED materials only; their built-in strain limits stay 0 so "
                "the card governs. Materials KEPT from the model do not get the card - they "
                "still use 'Plastic fail strain' as a plain Eps_max."),
    FAIL_TENS: ("A /FAIL/TENSSTRAIN card (et1 = onset of stress reduction, et2 = rupture) is added "
                "to LIBRARY-REPLACED materials only; kept materials still use 'Plastic fail strain'. "
                "If et1/et2 are left 0/empty, BOTH fall back to 'Plastic fail strain' (0 = solver "
                "default 1e20 = no failure ever). "
                "SoftBand: when et1 and et2 come out EQUAL (calibrating one strain), a value > 0 "
                "raises rupture above onset by that fraction (0.08 = et2 is 8% over et1) so stress "
                "ramps to zero over several cycles instead of a brittle one-cycle deletion - this "
                "eases the contact/mass-scaling impulse. 0 = off; distinct et1/et2 you type are left "
                "as-is. "
                "S_Flag sets the criterion AND strain measure: 23 = max principal true strain "
                "(default here); 13 = max principal engineering; 3 = max principal, strain def per "
                "property's Ismstr (implicit - changes with element formulation); "
                "1 = EQUIVALENT strain (the solver default if omitted - NOT principal!). FAILIP = "
                "integration points that must fail before shell deletion (this card has no Ifail_sh - "
                "FAILIP is its analog; FAILIP > 1 needs Radioss 2025+ input format)."),
}

# ==============================================================================
# HELP: ONE-LINE HINTS + STRUCTURED POP-UP DOCS (MK2 layout pass)
# ==============================================================================
# The long *_HELP paragraphs above stay as-is - the run manager writes them
# into every build's settings report, where dense prose is fine. The GUI now
# shows only a one-line *_HINT under each mode selector and moves the full
# story into a '?' pop-up rendered from the structured *_DOC text below.
# _DOC markup (parsed by GuiMixin._show_help): lines starting with '* ' are
# bullets; everything else is a paragraph; blank line = spacing.

TIE_HINT = {
    TIE_AUTO:   "Ties come from the *TIE cards in the source .inp; 'Fallback dist' covers ties without a tolerance.",
    TIE_SCOPED: "Ties come ONLY from the box below, one per line:  secondary > master : distance.",
    TIE_GLOBAL: "ONE universal TYPE2: any node bonds to any surface within 'Tie dist'.",
    TIE_NONE:   "No tie interfaces are written - parts interact through contact only.",
}
TIE_DOC = {
    TIE_AUTO: (
        "Ties are read from the *TIE cards in the source .inp.\n"
        "\n"
        "* Define them visually in PrePoMax (Find Contact Pairs or Selection).\n"
        "* Each *TIE's Position tolerance is its search distance.\n"
        "* 'Fallback dist' covers ties exported WITHOUT a Position tolerance.\n"
        "* If the .inp has no *TIE at all: the build warns and writes NO ties."),
    TIE_SCOPED: (
        "Ties come ONLY from the text box, one per line:\n"
        "\n"
        "    secondary > master : distance\n"
        "\n"
        "* Parts are matched by name substring or PID ('List Parts' shows both).\n"
        "* Use when each joint needs its own search distance and no PrePoMax ties exist.\n"
        "* Empty box = warning, NO ties written."),
    TIE_GLOBAL: (
        "ONE universal /INTER/TYPE2: any node may bond to any nearby surface within 'Tie dist'.\n"
        "\n"
        "* Blunt but quick - fine for simple stacks.\n"
        "* Risky when unrelated parts pass within the distance (they get welded).\n"
        "* Distance 0 = warning, NO tie written."),
    TIE_NONE: (
        "No tie interfaces are written.\n"
        "\n"
        "* Parts interact only through contact (and any rigid bodies / walls)."),
}

CONTACT_HINT = {
    CONTACT_T7:  "Universal node-to-surface contact - the robust default. Blind to shell-edge vs shell-edge.",
    CONTACT_T19: "TYPE7 + automatic edge-to-edge: fixes the free-edge blind spot, costs more.",
    CONTACT_T24: "Constant-stiffness contact: penetration never cuts the timestep; solids get zero gap.",
    CONTACT_NONE: "No general contact - only ties, model interfaces, rigid bodies and walls act.",
}
CONTACT_DOC = {
    CONTACT_T7: (
        "The legacy card, unchanged: one universal /INTER/TYPE7 - all nodes vs all external "
        "surfaces (Istf=4, Igap=2, Inacti=6).\n"
        "\n"
        "* Robust default for plate-dominated impact.\n"
        "* BLIND SPOT: shell EDGES sliding past each other (perpendicular plate edges, "
        "unstiffened rims) can pass through - the formulation is node-to-surface only.\n"
        "* Nonlinear stiffness can bite the timestep under deep penetration."),
    CONTACT_T19: (
        "One /INTER/TYPE19: internally two symmetric TYPE7s plus a TYPE11 edge-to-edge "
        "interface generated automatically from the same universal surface "
        "(single-surface form: surf_IDs=9999999, surf_IDm=0).\n"
        "\n"
        "* Fixes the TYPE7 edge blind spot - free deck and girder edges, impactor corners.\n"
        "* Costs more than TYPE7; Iedge=1 (external shell edges only) keeps it reasonable."),
    CONTACT_T24: (
        "One /INTER/TYPE24 single-surface contact (surf_ID1=9999999) with Iedge=1 "
        "shell-edge contact.\n"
        "\n"
        "* CONSTANT penalty stiffness: the timestep is never cut by contact penetration - "
        "attractive for heavily loaded decks.\n"
        "* Solids get a physical zero gap; initial penetrations are tracked, not fought.\n"
        "* Idel=2 drops failed segments from the contact.\n"
        "* Behaviour differs subtly from TYPE7 (gapless solids, constant K) - don't "
        "hot-swap formulations mid-study."),
    CONTACT_NONE: (
        "No general contact is written.\n"
        "\n"
        "* Parts interact only through ties, the model's own interfaces, rigid bodies "
        "and walls.\n"
        "* Anything else passes straight through everything."),
}

RBV_HINT = {
    RBV_EXPL:      "Writes /INIVEL/TRA (Vx Vy Vz) on the main node of the target /RBODY.",
    RBV_PROFILE:   "Smooth load-hold-unload /IMPDISP displacement profile on the /RBODY main node; times in seconds.",
    RBV_PROFILE_F: "Same profile as a /CLOAD force: 'Peak disp' is the PEAK FORCE (negative = push in -Z).",
    RBV_NONE:      "Nothing written - the deck keeps the model's own kinematics.",
}
RBV_DOC = {
    RBV_EXPL: (
        "The Vx Vy Vz field is written as /INIVEL/TRA on the MAIN node of the model's "
        "/RBODY (the PrePoMax reference point).\n"
        "\n"
        "* Requires EXACTLY ONE /RBODY in the deck (or a 'Target RP' naming one).\n"
        "* Zero /RBODY: define the rigid body in PrePoMax (RP at the CoG + rigid body tie).\n"
        "* Several /RBODY and no Target RP: ambiguous target.\n"
        "* In every failure case a RIGID WARNING is logged and NO velocity is written - "
        "including a Vx Vy Vz value that fails to parse."),
    RBV_PROFILE: (
        "Drives the /RBODY main node with a smooth load-hold-unload displacement profile "
        "(Rockwell-style push / hold / retract).\n"
        "\n"
        "* Builds a /FUNCT: a 0 -> 1 -> 0 eased trapezoid from Ramp/Hold/Ramp/Settle, and "
        "an /IMPDISP on the main node in the chosen direction, scaled by Peak disp.\n"
        "* The four times are in SECONDS. Smaller total = faster = higher strain rate - "
        "a rate sweep is just several builds with scaled times.\n"
        "* Same single-/RBODY requirement and warnings as the Explicit driver.\n"
        "* Run Tstop LONGER than the profile: a trailing zero point holds the indenter "
        "retracted through the settle.\n"
        "* Run Tstop SHORTER: the profile is truncated and a WARNING is logged."),
    RBV_PROFILE_F: (
        "Force control: the same smooth load-hold-unload SHAPE, but written as a /CLOAD "
        "on the /RBODY main node.\n"
        "\n"
        "* 'Peak disp' is reused as the PEAK FORCE, in deck force units.\n"
        "* Quarter model: apply a quarter of the real load (e.g. ~368 N for the 150 kgf "
        "HRC major load), and sign it negative to push in -Z.\n"
        "* More physical for hardness: you command the load, penetration is the result.\n"
        "* No kinematic constraint - a too-steep ramp lets the indenter overshoot. Keep "
        "ramps gentle and watch KE/IE.\n"
        "* Same single-/RBODY rule, Tstop fitting and warnings as the imposed-disp mode."),
    RBV_NONE: (
        "Nothing is written - the deck keeps exactly the kinematics the model defines.\n"
        "\n"
        "* The build still logs the deck's /RBODY and /INIVEL counts for the record."),
}

# ------------------------------------------------------------------------------
# v21.7: TRAVEL TABLE - the distances the Build tab reports a time for under the
# Explicit driver. Edit this tuple to change the rows; the table sizes itself.
# ------------------------------------------------------------------------------
TRAVEL_MM = (100.0, 500.0, 1000.0)
TRAVEL_DOC = (
    "Time for the impactor to cover a given distance at the velocity typed into "
    "Vx Vy Vz, checked against the run Time (Tstop).\n"
    "\n"
    "## What it computes\n"
    "* Speed is the VECTOR MAGNITUDE |V| = sqrt(Vx^2 + Vy^2 + Vz^2), i.e. travel "
    "along the actual direction of motion - not along one axis.\n"
    "* time = distance / |V|. Deck units: mm and mm/s, so the times are seconds "
    "and directly comparable with the Time field.\n"
    "* 'reached at NN% of the run' = that distance is covered NN% of the way "
    "through the solve. 'NOT reached' = Tstop ends before the impactor gets "
    "there.\n"
    "\n"
    "## What it does NOT do\n"
    "* Nothing here is written into the deck - it is arithmetic on two fields "
    "you already typed, shown before you spend a solve on them.\n"
    "* It is the FREE-FLIGHT distance: constant |V| with no contact and no "
    "gravity. Once the impactor hits something it slows down, so treat the "
    "numbers as the time to close a GAP, not as penetration depth.\n"
    "* The Vx Vy Vz box is parsed exactly as the build parses it (comma or "
    "space separated, missing components = 0), so the table can never disagree "
    "with what is written to /INIVEL/TRA.\n"
    "* Only the Explicit driver has one constant speed; under the "
    "load-hold-unload drivers the table is hidden.\n"
    "\n"
    "The distances are TRAVEL_MM in workspace_constants.py - edit that tuple to "
    "use your own set.")

FAIL_HINT = {
    FAIL_EPS:  "'Plastic fail strain' -> Eps_max in EVERY material; empty or 0 = no element failure anywhere.",
    FAIL_JC:   "/FAIL/JOHNSON on library-replaced materials; kept materials still use 'Plastic fail strain'.",
    FAIL_TENS: "/FAIL/TENSSTRAIN (et1 onset, et2 rupture) on library-replaced materials; kept ones use 'Plastic fail strain'.",
}
FAIL_DOC = {
    FAIL_EPS: (
        "'Plastic fail strain' is written into EVERY material's own card - no /FAIL card "
        "is added.\n"
        "\n"
        "* LAW2/PLAS_JOHNS: becomes Eps_max.\n"
        "* LAW36/PLAS_TAB: becomes Eps_p_max / Eps_t / Eps_m.\n"
        "* Applies to library-replaced AND kept-from-model materials alike.\n"
        "* Empty or 0 = NO element failure anywhere in the model."),
    FAIL_JC: (
        "A /FAIL/JOHNSON card (triaxiality-dependent) is added to LIBRARY-REPLACED "
        "materials only.\n"
        "\n"
        "* Parameters: D1-D5 (damage law), e0 (reference strain rate), Ifail_sh (shell "
        "failure flag).\n"
        "* The replaced materials' built-in strain limits stay 0, so the card governs.\n"
        "* Materials KEPT from the model do NOT get the card - they still use 'Plastic "
        "fail strain' as a plain Eps_max.\n"
        "* Elastic LAW1 library materials never get a failure card."),
    FAIL_TENS: (
        "A /FAIL/TENSSTRAIN card is added to LIBRARY-REPLACED materials only; kept "
        "materials still use 'Plastic fail strain'.\n"
        "\n"
        "## et1 / et2\n"
        "* et1 = onset of stress reduction, et2 = rupture (element deletion).\n"
        "* Left 0/empty: BOTH fall back to 'Plastic fail strain' (0 = solver default "
        "1e20 = no failure ever).\n"
        "\n"
        "## SoftBand\n"
        "* When et1 and et2 come out EQUAL (calibrating one strain), a value > 0 raises "
        "rupture above onset by that fraction (0.08 = et2 sits 8% over et1).\n"
        "* Stress then ramps to zero over several cycles instead of a brittle one-cycle "
        "deletion - eases the contact / mass-scaling impulse.\n"
        "* 0 = off. Distinct et1/et2 you type are always left as-is.\n"
        "\n"
        "## S_Flag  (criterion AND strain measure)\n"
        "* 23 = max principal TRUE strain (the default here).\n"
        "* 13 = max principal engineering strain.\n"
        "* 3  = max principal, strain definition per the property's Ismstr (implicit - "
        "changes with element formulation).\n"
        "* 1  = EQUIVALENT strain (the solver default if omitted - NOT principal!).\n"
        "\n"
        "## FAILIP\n"
        "* Integration points that must fail before shell deletion.\n"
        "* This card has no Ifail_sh - FAILIP is its analog.\n"
        "* FAILIP > 1 needs the Radioss 2025+ input format."),
}

# Inertia tab: "how this reaches the deck" - was a permanent 8-line block.
INERTIA_DOC = (
    "Build the impactor from box primitives in inertia_builder.py, export the /RBODY "
    "payload (mass, cx..cz, Jxx..Jxz), then point the field above at that JSON.\n"
    "\n"
    "On Build, by /RBODY count in the deck:\n"
    "* EXACTLY ONE (PrePoMax rigid body or Rigidified part): the payload MERGES into "
    "it - Mass, ICoG=3 and the six inertia terms are written into that block. The "
    "main node stays AT the model's reference point (payload cx/cy/cz are ignored on "
    "merge - v20.71.1). One body, real contact surface, correct inertia, one "
    "/INIVEL target.\n"
    "* NONE: a free-node body is created at the payload CG instead - it has NO "
    "contact surface (nothing can strike it); a loud caveat is logged.\n"
    "* SEVERAL: the build FAILS, naming the /RBODY ids - keep exactly one.\n"
    "\n"
    "Mass is taken verbatim - never faked by density.")

# ==============================================================================
# Engine stdout parsing for the Job Status board. Matches the cycle lines
#   NC= 70200 T= 1.0609E-01 DT= 1.5145E-06 ERR= -0.2% DM/M= 0.0000E+00
#   ELAPSED TIME= 1067.70 s  REMAINING TIME= 139.96 s
# exactly as OpenRadioss prints them (case/spacing tolerant).
# ==============================================================================
_NC_RE = re.compile(
    r"NC\s*=\s*(\d+)\s+T\s*=\s*([0-9.Ee+-]+)\s+DT\s*=\s*([0-9.Ee+-]+)"
    r"\s+ERR\s*=\s*(-?[0-9.]+)%\s+DM/M\s*=\s*([0-9.Ee+-]+)")
_TIME_RE = re.compile(
    r"ELAPSED\s+TIME\s*=\s*([0-9.]+)\s*s\s+REMAINING\s+TIME\s*=\s*([0-9.]+)\s*s",
    re.IGNORECASE)
_FAIL_MARKERS = ("ERROR TERMINATION", "** ERROR", "FORRTL: SEVERE", "SEGMENTATION FAULT")

# v20.67: explicit solver-kill markers. "** RUN KILLED" + MESSAGE ID lines are a
# controlled abort (e.g. TOTAL MASS ERROR, ID 207), not a crash - they must land
# as a terminal 'Killed' status carrying the reason, not a silent stop or a
# Python traceback from the runaway DM/M value on the final cycle line.
_KILL_RE = re.compile(r"\*\*\s*RUN\s+KILLED\s*:?\s*(.*)", re.IGNORECASE)
_MSGID_RE = re.compile(r"MESSAGE\s+ID\s*:?\s*(\d+)", re.IGNORECASE)

# v20.67: Fortran prints exponents wider than 2 digits without the 'E'
# ("1.6791+256"). Python's float() rejects that, which used to abort the whole
# console read on the last cycle before a mass-error kill. Match and repair it.
_FORT_EXP_RE = re.compile(r"^([+-]?\d*\.?\d+)([+-]\d{2,3})$")


def _fort_float(s):
    """float() that survives Fortran's E-less 3-digit exponents ('1.6791+256').

    A normal float parses normally; only the pathological overflow form is
    repaired by re-inserting the 'E'. Anything genuinely unparseable still
    raises, so real corruption is not silently swallowed.
    """
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        m = _FORT_EXP_RE.match(s)
        if m:
            return float(f"{m.group(1)}E{m.group(2)}")
        raise


# Warning thresholds for live run-health colouring
_ERR_WARN, _ERR_BAD = 5.0, 15.0      # |energy error| %
_DMM_WARN, _DMM_BAD = 0.02, 0.10     # added mass ratio


def _fmt_secs(v):
    """Seconds -> h:mm:ss / m:ss for the ETA column."""
    try:
        v = int(float(v))
    except Exception:
        return "-"
    m, s = divmod(v, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"



# CREATE_NO_WINDOW for subprocesses on Windows (0 elsewhere: creationflags is Windows only)
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

__all__ = [n for n in dir() if not n.startswith('__')]

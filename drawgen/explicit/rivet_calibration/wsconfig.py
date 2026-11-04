"""
wsconfig.py - read workspace_config.json and resolve the paths the rivet
calibration scripts need.

Shared by make_gauge_rings.py and relative_disp.py so both pick up the same
deck and run folder the GUI is currently pointed at, rather than needing paths
typed twice.

Resolution order for the config file:
    1. --config on the command line
    2. RIVET_CAL_CONFIG environment variable
    3. workspace_config.json in the parent directory (the normal case: this
       package sits in CURRENT_VERSION_MK1/rivet_calibration/)
    4. workspace_config.json in the current working directory
"""

import json
import os

CONFIG_NAME = "workspace_config.json"


class ConfigError(Exception):
    pass


def find_config(explicit=None):
    if explicit:
        if not os.path.isfile(explicit):
            raise ConfigError(f"config not found: {explicit}")
        return os.path.abspath(explicit)

    env = os.environ.get("RIVET_CAL_CONFIG")
    if env and os.path.isfile(env):
        return os.path.abspath(env)

    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(os.path.dirname(here), CONFIG_NAME),
                 os.path.join(os.getcwd(), CONFIG_NAME)):
        if os.path.isfile(cand):
            return os.path.abspath(cand)

    raise ConfigError(
        f"could not find {CONFIG_NAME}. Pass --config explicitly, or set "
        f"RIVET_CAL_CONFIG, or run from a folder alongside the GUI.")


def load(explicit=None):
    path = find_config(explicit)
    with open(path, "r", errors="replace") as fh:
        cfg = json.load(fh)
    cfg["__path__"] = path
    return cfg


def _norm(p):
    return os.path.normpath(p.replace("\\", "/")) if p else p


def rad_target(cfg):
    """The starter deck (<job>_0000.rad) the GUI last built or pointed at."""
    p = cfg.get("rad_target") or ""
    env = cfg.get("env_dirs", {}).get(cfg.get("run_target", ""), {})
    p = env.get("rad_target") or p
    if not p:
        raise ConfigError("no 'rad_target' in the config - build a model in the GUI first.")
    return _norm(p)


def out_dir(cfg):
    """The run folder the GUI writes results into."""
    p = cfg.get("out_dir") or ""
    env = cfg.get("env_dirs", {}).get(cfg.get("run_target", ""), {})
    p = env.get("out_dir") or p
    if not p:
        raise ConfigError("no 'out_dir' in the config.")
    return _norm(p)


def project_dir(cfg):
    p = cfg.get("project_dir") or ""
    if not p:
        raise ConfigError("no 'project_dir' in the config.")
    return _norm(p)


def jobname(cfg):
    """Job name as the GUI derives it: <job>_0000.rad -> <job>."""
    base = os.path.basename(rad_target(cfg))
    for suffix in ("_0000.rad", "_0001.rad", ".rad"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return os.path.splitext(base)[0]


def deck_folder(cfg):
    return os.path.dirname(rad_target(cfg))


def find_results_csv(cfg, run_folder=None, job=None):
    """Locate the th_to_csv output, matching the GUI's naming.

    The GUI writes '<job>_Results.csv'; th_to_csv itself writes '<job>T01.csv'.
    Searches the run folder and the deck subfolder beneath it, newest first.
    Returns None if nothing is found.
    """
    job = job or jobname(cfg)
    roots = []
    if run_folder:
        roots.append(run_folder)
    else:
        roots.append(out_dir(cfg))
        roots.append(deck_folder(cfg))

    names = [f"{job}_Results.csv", f"{job}T01.csv", f"{job}T01.CSV"]
    hits = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in names:
            p = os.path.join(root, name)
            if os.path.isfile(p):
                hits.append(p)
        # one level down - the GUI builds <out_dir>/<job>_bNN/
        try:
            for sub in os.listdir(root):
                subp = os.path.join(root, sub)
                if not os.path.isdir(subp):
                    continue
                for name in names:
                    p = os.path.join(subp, name)
                    if os.path.isfile(p):
                        hits.append(p)
        except OSError:
            pass

    if not hits:
        return None
    hits.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return hits[0]


def summary(cfg):
    lines = [f"config      {cfg['__path__']}"]
    for label, fn in (("project", project_dir), ("deck", rad_target),
                      ("run dir", out_dir), ("job", jobname)):
        try:
            lines.append(f"{label:<11} {fn(cfg)}")
        except ConfigError as e:
            lines.append(f"{label:<11} (unset: {e})")
    return "\n".join(lines)

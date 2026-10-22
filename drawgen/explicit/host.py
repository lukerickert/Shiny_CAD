"""Headless ORC**3 workspace: the build, run manager, solve and post-processing mixins on settings objects instead of
Tk variables.

Settings: every ORC**3 setting is an attribute holding a Var (get(), set()). apply(dict) sets them, snapshot() returns
them (the keys of the ORC**3 settings snapshot written to run.json). The library material slots are a list
(mat_slots: [[library entry, name in model], ...]) instead of the three slots MAT1 to MAT3.

Machine settings (ENV_KEYS) are kept in config.json > "explicit" by the web module; the others in the explicit
document (<name>.exp.json).
"""
import json
import os
import threading
import traceback
from datetime import datetime

from .constants import (CONTACT_T7, LHU_EASINGS, RBV_NONE, TIE_AUTO, _DMM_BAD, _DMM_WARN, _ERR_BAD, _ERR_WARN,
                        _fmt_secs)
from .modes import MODE_IMPACT
from .build import BuildMixin
from .materials import MaterialsMixin
from .runs import RunMixin
from .solve import SolveMixin
from .post import PostMixin

LOCAL = "Local (Windows)"          # run_target values (ORC**3 labels)
REMOTE = "Remote (Linux)"
HISTORY_MAX = 200

# ORC**3 defaults (workspace.py with an empty configuration), except the analysis type and the server fields
DEFAULTS = {
    "analysis_mode": MODE_IMPACT,
    "project_dir": "", "run_desc": "", "run_notes": "",
    "inp_path": "", "downgrade_quad": False, "out_dir": "",
    "test_mode": "Standard Assembly Impact", "floor_z": "0.0", "fric": "0.2", "tstop": "0.1",
    "dt_min": "0", "dt_target_dmm": "2", "anim_frames": "100",
    "fail_strain": "0.30", "fail_model": "Equivalent plastic strain",
    "jc_d1": "0.0", "jc_d2": "0.0", "jc_d3": "0.0", "jc_d4": "0.0", "jc_d5": "0.0", "jc_eps0": "1.0", "jc_ifail_sh": "1",
    "ts_et1": "0.0", "ts_et2": "0.0", "ts_soften": "0.0", "ts_sflag": "23", "ts_failip": "1",
    "tie_dist": "0.0", "tie_mode": TIE_AUTO, "tie_pairs": "",
    "gravity": True, "build_subdirs": True, "purge_prev": False, "align_norms": True,
    "contact_mode": CONTACT_T7, "apply_vel_model": True,
    "rigid_vel_mode": RBV_NONE, "rigid_vel": "", "rigid_rp_target": "", "rigid_part": "", "point_mass_json": "",
    "lhu_peak": "-0.1", "lhu_dir": "Z", "lhu_rampup": "1.0", "lhu_hold": "0.5", "lhu_rampdn": "1.0",
    "lhu_settle": "1.0", "lhu_easing": LHU_EASINGS[0], "lhu_npramp": "50",
    "rad_target": "", "plot_ke": True, "extract_strains": True, "pv_images": True,
    # machine settings (ENV_KEYS)
    "run_target": LOCAL, "ssh_threads": "4", "ssh_host": "", "ssh_port": "22", "stream_remote": True,
    "remote_env": "", "remote_exec": "", "remote_scratch": "", "share_map": "",
    "pvbatch_path": "", "paraview_path": "", "or_exec": "",
}
ENV_KEYS = ("run_target", "ssh_threads", "ssh_host", "ssh_port", "stream_remote", "remote_env", "remote_exec",
            "remote_scratch", "share_map", "pvbatch_path", "paraview_path", "or_exec")
DEFAULT_SLOTS = [["None (Use PrePoMax Data)", "MAT1"], ["None (Use PrePoMax Data)", "MAT2"],
                 ["None (Use PrePoMax Data)", "MAT3"]]


class Var(object):
    """Value holder with the get() / set() of a Tk variable."""
    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


def _coerce(key, v):
    d = DEFAULTS.get(key)
    if isinstance(d, bool):
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)
    return "" if v is None else str(v)


class Workspace(BuildMixin, MaterialsMixin, RunMixin, SolveMixin, PostMixin):
    def __init__(self, on_save=None, history_path=None, log_cb=None):
        for k, v in DEFAULTS.items():
            setattr(self, k, Var(v))
        self.mat_slots = [list(s) for s in DEFAULT_SLOTS]
        self._on_save = on_save
        self._log_cb = log_cb
        self.history_path = history_path
        self._log_lock = threading.Lock()
        self.logs = []                 # [(seq, text)]
        self.log_seq = 0
        self.job_queue = []
        self.local_abort = False
        self.remote_abort = False
        self._busy_envs = set()
        self._remote_tail_proc = None
        self._local_proc = None
        self.job_status = {}
        self.job_order = []
        self.job_folders = {}
        self.job_envs = {}
        self._status_dirty = False
        self.ke_curves = {}
        self.server_queue = None
        self.min_dt_offer = None
        self.last_build = None
        self.building = False
        self.tasks = {}               # name -> running thread (post-processing commands)
        self.run_history = []
        self._history_load()

    # ------------------------------------------------------------------ settings
    def apply(self, settings):
        """Set the settings present in the dict (unknown keys are ignored)."""
        for k, v in (settings or {}).items():
            if k in DEFAULTS:
                getattr(self, k).set(_coerce(k, v))
        if "mat_slots" in (settings or {}):
            self.mat_slots = [[str(a or ""), str(b or "")] for a, b in (settings.get("mat_slots") or [])]
        elif any(k in (settings or {}) for k in ("mat1", "mat1_name")):      # ORC**3 snapshot
            self.mat_slots = [[settings.get("mat%d" % i, DEFAULT_SLOTS[i - 1][0]),
                               settings.get("mat%d_name" % i, DEFAULT_SLOTS[i - 1][1])] for i in (1, 2, 3)]
        self._tie_text = self.tie_pairs.get().strip()

    def _mat_slots(self):
        return [(Var(a), Var(b)) for a, b in self.mat_slots]

    def _settings_snapshot(self):
        """All settings as a dict (the ORC**3 snapshot keys; mat1..mat3 for the first three library slots)."""
        out = {k: getattr(self, k).get() for k in DEFAULTS}
        out["mat_slots"] = [list(s) for s in self.mat_slots]
        for i, (a, b) in enumerate(self.mat_slots[:3], start=1):
            out["mat%d" % i], out["mat%d_name" % i] = a, b
        out["self_contact"] = self.contact_mode.get() != "None"
        out["job_queue"] = list(self.job_queue)
        return out

    snapshot = _settings_snapshot

    def save_state(self):
        if self._on_save:
            try:
                self._on_save(self._settings_snapshot())
            except Exception as e:
                self.log_msg("Settings could not be saved: %s" % e)

    # ------------------------------------------------------------------ log
    def log_msg(self, message):
        """Console line; also appended to <run folder>/console.log when Output Dir is a run folder (ORC**3)."""
        text = str(message)
        with self._log_lock:
            for ln in text.split("\n"):
                self.log_seq += 1
                self.logs.append((self.log_seq, ln))
            if len(self.logs) > 20000:
                del self.logs[:len(self.logs) - 20000]
        if self._log_cb:
            try:
                self._log_cb(text)
            except Exception:
                pass
        try:
            od = self.out_dir.get()
            if od != getattr(self, "_logf_dir", None):
                self._logf_dir = od
                self._logf_is_run = bool(od) and os.path.isfile(os.path.join(od, "run.json"))
                self._logf_new_session = True
            if self._logf_is_run:
                with open(os.path.join(self._logf_dir, "console.log"), "a", encoding="utf-8", errors="replace") as lf:
                    if getattr(self, "_logf_new_session", False):
                        lf.write(f"\n===== session {datetime.now().isoformat(timespec='seconds')} =====\n")
                        self._logf_new_session = False
                    lf.write(text + "\n")
        except Exception:
            pass

    def log_since(self, seq):
        with self._log_lock:
            return [(s, t) for s, t in self.logs if s > seq]

    # ------------------------------------------------------------------ Tk replacements
    def after(self, _ms, fn, *args):
        fn(*args)

    def _refresh_status_tree(self):
        pass

    def _ticker_start(self):
        pass

    def _ticker_stop(self):
        pass

    def _maybe_ticker_stop(self):
        pass

    @property
    def _status_ticker(self):
        return bool(self._busy_envs)

    def _ke_add_curve(self, jobname, t, ke, ie, src):
        self.ke_curves[jobname] = {"t": list(t), "ke": list(ke), "ie": list(ie) if ie is not None else None, "src": src}

    def _build_done(self, final_rad_file, deck_dir, model_name):
        self.last_build = {"rad": final_rad_file.replace("\\", "/"), "dir": deck_dir.replace("\\", "/"),
                           "job": model_name, "time": datetime.now().isoformat(timespec="seconds")}

    # ------------------------------------------------------------------ run history (ORC**3 Solve tab)
    def _history_load(self):
        self.run_history = []
        p = self.history_path
        try:
            if p and os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, list):
                    self.run_history = [e for e in data if isinstance(e, dict)]
        except Exception as e:
            self.log_msg(f"Run history: could not read {os.path.basename(p)}: {e}")

    def set_history_path(self, path):
        if path != self.history_path:
            self.history_path = path
            self._history_load()

    def _history_save(self):
        if not self.history_path:
            return
        try:
            os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
            with open(self.history_path, "w", encoding="utf-8") as fh:
                json.dump(self.run_history, fh, indent=1)
        except Exception as e:
            self.log_msg(f"Run history: could not write {os.path.basename(self.history_path)}: {e}")

    def _history_add(self, jobname, status, folder, env, err=None, dmm=None, elapsed=None, nc=None):
        entry = {"job": jobname, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "status": status, "env": env,
                 "folder": folder, "err": err, "dmm": dmm, "elapsed": elapsed, "nc": nc}
        self.run_history.append(entry)
        del self.run_history[:-HISTORY_MAX]
        self._history_save()

    # ------------------------------------------------------------------ OpenRadioss executables
    def _or_exe(self, name):
        """starter, engine, anim_to_vtk, th_to_csv: <name>_win64 (Windows) or <name>_linux64_gf, in the exec folder
        when one is set, else found on PATH (ORC**3)."""
        exe = name + ("_win64" if os.name == "nt" else "_linux64_gf")
        d = (self.or_exec.get() or "").strip().strip('"')
        if not d:
            return exe
        for ext in ((".exe", ".cmd", ".bat") if os.name == "nt" else ("",)):
            p = os.path.join(d, exe + ext)
            if os.path.isfile(p):
                return p
        return os.path.join(d, exe + (".exe" if os.name == "nt" else ""))

    def _or_env(self):
        """Environment of the local solver processes: None (inherited) without an exec folder; with one, the exec
        folder and the OpenRadioss runtime libraries on PATH, RAD_CFG_PATH and RAD_H3D_PATH, KMP_STACKSIZE."""
        d = (self.or_exec.get() or "").strip().strip('"')
        if not d:
            return None
        env = dict(os.environ)
        root = os.path.dirname(os.path.normpath(d))
        plat = "win64" if os.name == "nt" else "linux64"
        paths = [d]
        libs = [os.path.join(root, "extlib", "hm_reader", plat), os.path.join(root, "extlib", "h3d", "lib", plat)]
        if os.name == "nt":
            libs.append(os.path.join(root, "extlib", "intelOneAPI_runtime", "win64"))
            paths += [x for x in libs if os.path.isdir(x)]
        else:
            ld = [x for x in libs if os.path.isdir(x)]
            if ld:
                env["LD_LIBRARY_PATH"] = os.pathsep.join(ld + [env.get("LD_LIBRARY_PATH", "")]).rstrip(os.pathsep)
        env["PATH"] = os.pathsep.join(paths + [env.get("PATH", "")])
        cfg = os.path.join(root, "hm_cfg_files")
        if os.path.isdir(cfg):
            env.setdefault("RAD_CFG_PATH", cfg)
        h3d = os.path.join(root, "extlib", "h3d", "lib", plat)
        if os.path.isdir(h3d):
            env.setdefault("RAD_H3D_PATH", h3d)
        env.setdefault("KMP_STACKSIZE", "400m")
        env.setdefault("OMP_STACKSIZE", "400m")
        return env

    # ------------------------------------------------------------------ commands
    def execute_build(self):
        """Build in a thread (ORC**3 execute_build). Returns False when a build is running."""
        if self.building:
            self.log_msg("Build: a build is already running.")
            return False
        self.building = True
        self.save_state()
        self._tie_text = self.tie_pairs.get().strip()

        def work():
            try:
                self._build_thread()
            except Exception as e:
                self.log_msg(f"Build Error: {e}\n{traceback.format_exc()}")
            finally:
                self.building = False
        threading.Thread(target=work, daemon=True).start()
        return True

    def run_task(self, name, fn, *args):
        """Runs a post-processing command in a thread; one per name at a time."""
        t = self.tasks.get(name)
        if t is not None and t.is_alive():
            self.log_msg(f"{name}: already running.")
            return False

        def work():
            try:
                fn(*args)
            except Exception as e:
                self.log_msg(f"{name} error: {e}\n{traceback.format_exc()}")
        t = threading.Thread(target=work, daemon=True)
        self.tasks[name] = t
        t.start()
        return True

    def status(self):
        """Job status board (ORC**3 _refresh_status_tree): rows of the current batches, then the queued decks."""
        rows = []
        for jn in list(self.job_order):
            rec = self.job_status.get(jn) or {}
            st = rec.get("status", "?")
            t, tstop = rec.get("t"), rec.get("tstop")
            prog = None
            if t is not None and tstop:
                prog = min(100.0, 100.0 * t / tstop)
            elif st == "Done":
                prog = 100.0
            eta = rec.get("eta")
            if st in ("Done", "Failed", "Killed", "Skipped", "Starter done"):
                eta = None
            if st in ("Failed", "Killed"):
                tag = "failed"
            elif st in ("Done", "Skipped", "Starter done"):
                tag = "done"
            elif st == "Queued":
                tag = "queued"
            else:
                tag = "running"
                e = abs(rec["err"]) if rec.get("err") is not None else 0.0
                d = rec.get("dmm") or 0.0
                if e >= _ERR_BAD or d >= _DMM_BAD:
                    tag = "bad"
                elif e >= _ERR_WARN or d >= _DMM_WARN:
                    tag = "warn"
            rows.append({"id": "s::" + jn, "job": jn, "status": st, "note": rec.get("note") or "", "progress": prog,
                         "t": t, "tstop": tstop, "dt": rec.get("dt"), "nc": rec.get("nc"), "eta": eta,
                         "eta_text": _fmt_secs(eta) if eta is not None else "", "elapsed": rec.get("elapsed"),
                         "err": rec.get("err"), "dmm": rec.get("dmm"), "tag": tag,
                         "folder": (self.job_folders.get(jn) or "").replace("\\", "/"), "env": self.job_envs.get(jn, "")})
        covered = set(self.job_order)
        for i, fp in enumerate(self.job_queue, 1):
            jn = os.path.basename(fp).replace("_0000.rad", "")
            if jn in covered:
                continue
            rows.append({"id": "q::" + fp, "job": jn, "status": "Queued #%d" % i, "note": fp, "tag": "queued",
                         "folder": os.path.dirname(fp).replace("\\", "/"), "progress": None})
        return {"rows": rows, "busy": sorted(self._busy_envs), "building": self.building,
                "queue": list(self.job_queue), "server_queue": self.server_queue,
                "min_dt_offer": self.min_dt_offer, "last_build": self.last_build,
                "tasks": sorted(k for k, t in self.tasks.items() if t.is_alive()),
                "history": list(reversed(self.run_history[-50:]))}

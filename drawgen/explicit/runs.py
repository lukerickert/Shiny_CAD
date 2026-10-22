"""Run manager of the explicit analysis (ORC**3 workspace_runmanager.py): numbered run folders, run.json,
the settings report, purge and clean.

RunMixin of the headless workspace (host.Workspace)."""

import os
import json
import shutil
import glob
import re
from datetime import datetime, date

from .constants import (CONTACT_HELP, CONTACT_T7, FAIL_HELP, FAIL_JC, FAIL_TENS, MATERIAL_LIBRARY, RBV_EXPL, RBV_HELP, RBV_PROFILE, RBV_PROFILE_F, TIE_HELP, TIE_SCOPED, WORKSPACE_NAME, WORKSPACE_TAGLINE, WORKSPACE_VERSION)


class RunMixin:
    # =========================================================================
    # RUN MANAGER
    # =========================================================================
    # Regenerable solver output, safe to purge (inputs can always be re-run):
    # animation files (<job>A0001...), converted .vtk/.vtk.series, restart .rst,
    # time-history T-files, and the temp extractor script. Decks, model/,
    # run.json, .out listings, CSV summaries and PNG plots are always kept.
    @staticmethod
    def _is_purgeable(name):
        low = name.lower()
        if low.endswith((".vtk", ".vtk.series", ".rst")):
            return True
        if name == "_extract_principal_strain.py":
            return True
        # OpenRadioss A-files (<job>A0001) and T-files (<job>T01) have no extension.
        return "." not in name and re.search(r"[AT]\d{2,}$", name) is not None

    def _runs_root(self):
        p = self.project_dir.get().strip()
        return os.path.join(p, "runs") if p else None

    def _parse_prepomax_version(self, inp_file):
        """PrePoMax stamps its version in the exported .inp header comments.
        Recorded because .pmx files are NOT backward compatible between versions —
        this tells you which PrePoMax build can reopen the archived model."""
        try:
            with open(inp_file, "r", errors="ignore") as f:
                for _ in range(100):
                    line = f.readline()
                    if not line:
                        break
                    m = re.search(r"PrePoMax\s+v?([0-9][\w.\-]*)", line, re.IGNORECASE)
                    if m:
                        return m.group(1)
        except Exception:
            pass
        return None

    def cmd_new_run(self):
        root = self._runs_root()
        if not root:
            self.log_msg("Run Manager: set a Project Dir first."); return
        desc = self.run_desc.get().strip()
        if not desc:
            self.log_msg("Run Manager: enter a short Description for the run."); return

        # Next sequence number from existing folders (self-maintaining).
        seq = 0
        if os.path.isdir(root):
            for name in os.listdir(root):
                m = re.match(r"\d{4}-\d{2}-\d{2}_r(\d+)_", name)
                if m:
                    seq = max(seq, int(m.group(1)))
        seq += 1
        slug = re.sub(r"[^a-z0-9]+", "-", desc.lower()).strip("-")[:40] or "run"
        run_dir = os.path.join(root, f"{date.today().isoformat()}_r{seq:03d}_{slug}")
        model_dir = os.path.join(run_dir, "model")
        try:
            os.makedirs(model_dir)
        except Exception as e:
            self.log_msg(f"Run Manager: could not create {run_dir}: {e}"); return

        meta = {
            "created": datetime.now().isoformat(timespec="seconds"),
            "description": desc,
            "notes": self.run_notes.get().strip(),
            "source_inp": "", "archived_inp": "",
            "archived_pmx": "", "prepomax_version": None,
            "builds": [],
        }

        # Archive the source model. The .inp is what the build consumes; the
        # sibling .pmx (same stem, same folder) is the editable PrePoMax project —
        # archived so the exact model survives even if the working file evolves.
        inp = self.inp_path.get().strip()
        if inp and os.path.isfile(inp):
            meta["source_inp"] = inp
            try:
                shutil.copy2(inp, model_dir)
                meta["archived_inp"] = os.path.basename(inp)
            except Exception as e:
                self.log_msg(f"Run Manager: could not archive .inp: {e}")
            ver = self._parse_prepomax_version(inp)
            meta["prepomax_version"] = ver
            pmx = os.path.splitext(inp)[0] + ".pmx"
            if os.path.isfile(pmx):
                try:
                    shutil.copy2(pmx, model_dir)
                    meta["archived_pmx"] = os.path.basename(pmx)
                    self.log_msg(f"Run Manager: archived {os.path.basename(pmx)} "
                                 f"(PrePoMax {ver or 'version unknown'} — .pmx files are version-bound; "
                                 f"keep a portable copy of this PrePoMax version to reopen it).")
                except Exception as e:
                    self.log_msg(f"Run Manager: could not archive .pmx: {e}")
            else:
                self.log_msg("Run Manager: no sibling .pmx found next to the .inp — "
                             "only the exported .inp is archived. If you need to re-edit this "
                             "model later, save the .pmx alongside the .inp before creating the run.")
            if ver:
                self.log_msg(f"Run Manager: PrePoMax version recorded from .inp header: {ver}")
            else:
                self.log_msg("Run Manager: PrePoMax version not found in the .inp header.")
        else:
            self.log_msg("Run Manager: no source .inp selected — run created empty; "
                         "select the .inp and it will be archived at BUILD time.")

        try:
            with open(os.path.join(run_dir, "run.json"), "w") as f:
                json.dump(meta, f, indent=2)
        except Exception as e:
            self.log_msg(f"Run Manager: could not write run.json: {e}")

        self.out_dir.set(run_dir.replace("\\", "/"))
        self.save_state()
        self.log_msg(f"Run Manager: created {run_dir}")
        self.log_msg("Run Manager: Output Dir now points at this run — BUILD and RUN as normal.")
        return run_dir

    def _purge_previous_builds(self, root, base_name, current_bno):
        """Delete OLDER builds of this model from the run folder: per-build
        subfolders <base>_bNN/ (decks, settings.txt AND any solver results in
        them) plus legacy loose files <base>_bNN* from pre-subfolder builds.
        The current build (bno == current_bno) and anything not matching the
        strict <base>_b<digits> pattern (run.json, model/, console.log, other
        models) is never touched."""
        dpat = re.compile(rf"^{re.escape(base_name)}_b(\d+)$")
        fpat = re.compile(rf"^{re.escape(base_name)}_b(\d+)")
        removed = 0
        try:
            names = sorted(os.listdir(root))
        except Exception as e:
            self.log_msg(f"Purge: could not list {root}: {e}")
            return
        for nm in names:
            full = os.path.join(root, nm)
            if os.path.isdir(full):
                m = dpat.match(nm)
                if m and int(m.group(1)) < current_bno:
                    try:
                        shutil.rmtree(full)
                        removed += 1
                        self.log_msg(f"Purge: removed previous build folder {nm}/")
                    except Exception as e:
                        self.log_msg(f"Purge: could not remove {nm}/: {e}")
            elif os.path.isfile(full):
                m = fpat.match(nm)
                if m and int(m.group(1)) < current_bno:
                    try:
                        os.remove(full)
                        removed += 1
                    except Exception as e:
                        self.log_msg(f"Purge: could not remove {nm}: {e}")
        self.log_msg(f"Purge: {removed} previous build item(s) removed."
                     if removed else "Purge: nothing older to remove.")

    # Human-readable meanings for the TENSSTRAIN S_Flag values the GUI offers.
    _SFLAG_MEANING = {
        1:  "EQUIVALENT strain (von Mises-type scalar; sign-blind, so it also "
            "fires on the compression side of plastic hinges where no tearing "
            "is physically possible - NOT a principal-strain criterion)",
        3:  "max principal tensile strain, measured per the property's Ismstr "
            "(IMPLICIT: large-strain shells accumulate ~true strain, small-strain "
            "Ismstr=1 behaves like engineering - the threshold's meaning changes "
            "if the element formulation changes)",
        13: "max principal tensile strain, converted to ENGINEERING measure "
            "(e = dL/L0) before comparing to et1/et2",
        23: "max principal tensile strain, converted to TRUE (logarithmic) "
            "measure (eps = ln(1+e)) before comparing to et1/et2 - unambiguous "
            "across meshes and element formulations",
    }

    def _settings_report(self, model_name):
        """A detailed, self-explanatory record of every Build-tab selection:
        what was chosen AND what that choice does to the deck. Written next to
        the decks so any build can be understood months later without the GUI,
        the config file or this script."""
        import textwrap
        W = 96
        IND = " " * 4

        def wrap(txt, indent=IND):
            return textwrap.fill(" ".join(str(txt).split()), width=W,
                                 initial_indent=indent, subsequent_indent=indent)

        def onoff(v):
            return "ON" if v else "OFF"

        L = []
        L.append("=" * W)
        L.append(f"BUILD SETTINGS REPORT - {model_name}")
        L.append("=" * W)
        L.append(f"Generated : {datetime.now().isoformat(timespec='seconds')}")
        L.append(f"Script    : SHINYCAD Explicit tab, {WORKSPACE_NAME} {WORKSPACE_VERSION} core  ({WORKSPACE_TAGLINE})")
        L.append(f"Source    : {self.inp_path.get()}")
        L.append(f"Output    : {self.out_dir.get()}")
        L.append(f"Units     : Mg / mm / s (stress in MPa, density in Mg/mm^3, velocity in mm/s)")
        L.append("")

        L.append("-" * W)
        L.append("GENERAL")
        L.append("-" * W)
        L.append(f"Mode: {self.test_mode.get()}")
        if "Rigid Floor" in self.test_mode.get():
            L.append(wrap(f"An infinite rigid wall is added at Z = {self.floor_z.get()} for a "
                          "drop-test setup; everything falling reacts against it."))
        else:
            L.append(wrap("No extra rigid floor is injected - the model's own supports/BCs "
                          "carry the impact."))
        L.append(f"Time (Tstop): {self.tstop.get()} s")
        try:
            _dtm = float(self.dt_min.get())
        except Exception:
            _dtm = 0.0
        if _dtm > 0:
            L.append(f"Mass scaling: /DT/NODA/CST DTmin = {_dtm:g} s (solver adds nodal mass to hold "
                     f"the timestep at this floor; watch added-mass % and KE/IE).")
        else:
            L.append("Mass scaling: OFF (Min dt = 0) - raw mesh-limited timestep; a sub-mm mesh may "
                     "need millions of steps. Set Min dt to a target timestep to make it affordable.")
        L.append(wrap("Physical simulated duration written to the engine /RUN card. The event "
                      "must complete (impact + rebound/arrest) within this window."))
        L.append(f"Frames: {self.anim_frames.get()}")
        L.append(wrap("Number of animation states over Tstop (/ANIM/DT = Tstop/frames). More "
                      "frames = finer post-processing time resolution, larger A-files."))
        L.append(f"Fric: {self.fric.get()}")
        L.append(wrap("Coulomb friction coefficient on the general contact interface "
                      "(whichever Contact mode is selected) and the rigid floor. "
                      "Steel-on-steel is typically 0.1-0.3."))
        L.append("")

        L.append("-" * W)
        L.append("MATERIALS")
        L.append("-" * W)
        L.append(wrap("Library selections REPLACE the matching material from the model "
                      "(matched by 'Name in model') with the workspace's own /MAT card + "
                      "hardening curve; the original curve is stripped. 'None' keeps the "
                      "PrePoMax-exported material untouched.", indent=""))
        for slot, (mv, nv) in enumerate(self._mat_slots(), start=1):
            sel = mv.get()
            if sel.startswith("None"):
                L.append(f"MAT{slot}: {sel}")
            else:
                entry = MATERIAL_LIBRARY.get(sel) or {}
                law = str(entry.get("law", "LAW36")).upper()
                if law == "LAW2":
                    detail = (f"LAW2 Johnson-Cook: a={entry.get('a')} b={entry.get('b')} n={entry.get('n')} "
                              f"c={entry.get('c')} eps0={entry.get('eps0')} /s")
                elif law == "LAW1":
                    detail = f"LAW1 elastic (E={entry.get('E')}, nu={entry.get('nu')}; no yield, no /FAIL card)"
                elif entry.get("cs_D") and entry.get("rates"):
                    detail = (f"LAW36 rate-dependent: base curve + Cowper-Symonds DIF at eps_dot = "
                              f"{', '.join(f'{r:g}' for r in sorted(entry['rates'])[:4])} /s "
                              f"(D={entry['cs_D']:g}, q={entry['cs_q']:g})")
                else:
                    detail = "LAW36 tabulated (single static curve)"
                L.append(f"MAT{slot}: '{sel}'  (replaces model material named '{nv.get()}')")
                L.append(f"       {detail}")
        L.append("")

        L.append("-" * W)
        L.append("FAILURE")
        L.append("-" * W)
        fm = self.fail_model.get()
        L.append(f"Model: {fm}")
        L.append(wrap(FAIL_HELP.get(fm, "")))
        L.append(f"Plastic fail strain: {self.fail_strain.get() or '(empty)'}")
        if fm == FAIL_JC:
            L.append(f"Johnson-Cook: D1={self.jc_d1.get()} D2={self.jc_d2.get()} D3={self.jc_d3.get()} "
                     f"D4={self.jc_d4.get()} D5={self.jc_d5.get()} e0={self.jc_eps0.get()} "
                     f"Ifail_sh={self.jc_ifail_sh.get()}")
        elif fm == FAIL_TENS:
            et1, et2, note = self._resolve_tens_thresholds()
            L.append(f"TENSSTRAIN fields as entered: et1={self.ts_et1.get() or '(empty)'} "
                     f"et2={self.ts_et2.get() or '(empty)'} "
                     f"SoftBand={self.ts_soften.get() or '(empty)'}")
            L.append(f"TENSSTRAIN as WRITTEN to the deck: EPSILON_T1={et1:g}  EPSILON_T2={et2:g}")
            if note:
                L.append(wrap(f"NOTE: {note}."))
            L.append(wrap("EPSILON_T1 = strain at onset of stress reduction (damage starts), "
                          "EPSILON_T2 = rupture (element deleted). Equal values = brittle "
                          "deletion the moment the threshold is reached; a gap gives a "
                          "softening ramp between them."))
            try:
                sflag = int(float(self.ts_sflag.get()))
            except Exception:
                sflag = 23
            L.append(f"S_Flag: {sflag}")
            L.append(wrap(self._SFLAG_MEANING.get(
                sflag, "see the OpenRadioss /FAIL/TENSSTRAIN documentation for this value")))
            L.append(wrap("Thresholds are TOTAL strain (elastic + plastic). For S355 the "
                          "elastic part is ~0.0017, so a plastic-strain criterion should be "
                          "raised by that amount when entered here."))
            L.append(f"FAILIP: {self.ts_failip.get()}")
            L.append(wrap("Integration points through the shell thickness that must fail "
                          "before the element is deleted (1 = first surface to reach the "
                          "threshold kills the element)."))
        L.append("")

        L.append("-" * W)
        L.append("OPTIONS")
        L.append("-" * W)
        L.append(f"Gravity: {onoff(self.gravity.get())}")
        if self.gravity.get():
            try:
                _ts = float(self.tstop.get())
                L.append(f"  -Z, 9810 mm/s^2, ramped 0..{_ts*0.05:.5g}s (5% of tstop) then held.")
            except Exception:
                L.append("  -Z, 9810 mm/s^2, ramped over first 5% of tstop then held.")
        L.append(wrap("Writes /GRAV (9810 mm/s^2, -Z). OFF is NON-CONSERVATIVE for dropped-"
                      "object cases: no sustained dead-load of the object on the deformed "
                      "structure after initial arrest."))
        L.append(f"Contact: {self.contact_mode.get()}")
        L.append(wrap(CONTACT_HELP.get(self.contact_mode.get(), "")))
        if self.contact_mode.get() == CONTACT_T7:
            if self._erosion_active():
                L.append(wrap("Erosion coupling: the active failure model deletes elements, so this "
                              "TYPE7 is written with Idel=1 (dead segments AND orphaned secondary "
                              "nodes leave the interface) and the engine deck carries a "
                              "/DT/INTER/DEL backstop. Without these, an orphaned node drives "
                              "/DT/NODA/CST added mass to overflow: MESSAGE ID 207, TOTAL MASS "
                              "ERROR (v20.67 fix)."))
            else:
                L.append(wrap("Erosion coupling: no deleting failure model is active, so TYPE7 uses "
                              "Idel=0 and no /DT/INTER/DEL backstop is written. Enabling a failure "
                              "model that erodes elements switches both on automatically."))
        L.append(f"Heal Normals: {onoff(self.align_norms.get())}")
        L.append(wrap("Re-orients shell element winding per connected patch so normals are "
                      "consistent - inconsistent normals break contact thickness and "
                      "pressure signs."))
        L.append(f"Disp -> Velocity: {onoff(self.apply_vel_model.get())}")
        L.append(wrap("Converts the model's imposed-displacement (/IMPDISP) loading into an "
                      "equivalent constant-velocity /IMPVEL over Tstop - the standard "
                      "quasi-static-to-explicit conversion."))
        L.append(f"Subfolder per build: {onoff(self.build_subdirs.get())}   |   "
                 f"Purge older builds: {onoff(self.purge_prev.get())}")
        L.append(wrap("Subfolder: decks + this report + solver output live in "
                      "<OutputDir>/<MODEL_bNN>/. Purge: after a successful build, OLDER "
                      "build folders and legacy loose bNN files of this model are deleted."))
        L.append("")

        L.append("-" * W)
        L.append("IMPACTOR VELOCITY (model rigid body)")
        L.append("-" * W)
        L.append(f"Mode: {self.rigid_vel_mode.get()}")
        L.append(wrap(RBV_HELP.get(self.rigid_vel_mode.get(), "")))
        if self.rigid_vel_mode.get() == RBV_EXPL:
            L.append(f"Vx Vy Vz: {self.rigid_vel.get()}  (mm/s), written on the model /RBODY main node")
        elif self.rigid_vel_mode.get() in (RBV_PROFILE, RBV_PROFILE_F):
            _is_force = self.rigid_vel_mode.get() == RBV_PROFILE_F
            _pklbl = "peak force" if _is_force else "peak disp"
            _card = "/CLOAD" if _is_force else "/IMPDISP"
            L.append(f"Profile ({'force' if _is_force else 'displacement'}): {_pklbl} "
                     f"{self.lhu_peak.get()} in {self.lhu_dir.get()}, "
                     f"{self.lhu_easing.get()} easing, {self.lhu_npramp.get()} pts/ramp")
            L.append(f"  times [s]: ramp-up {self.lhu_rampup.get()}, hold {self.lhu_hold.get()}, "
                     f"ramp-down {self.lhu_rampdn.get()}, settle {self.lhu_settle.get()}")
            try:
                tot = (float(self.lhu_rampup.get()) + float(self.lhu_hold.get()) +
                       float(self.lhu_rampdn.get()) + float(self.lhu_settle.get()))
                L.append(f"  profile total {tot:g}s vs run Tstop {self.tstop.get()}s "
                         f"({_card} + /FUNCT on the /RBODY main node)")
            except Exception:
                pass
        _rp = (self.rigid_part.get() or "").strip()
        if _rp:
            L.append(wrap(f"Rigidify part(s): {_rp}  -> each resolved part gets a /RBODY "
                          f"(9970201+) over a /GRNOD/PART (9970101+) of its nodes, with a free "
                          f"master /NODE (9970001+); ICoG default 1 puts the master at the CoG and "
                          f"keeps the part's structural mass. Adds one /RBODY per part."))
        L.append("")

        L.append("-" * W)
        L.append("TIES (bonded connections)")
        L.append("-" * W)
        L.append(f"Tie Mode: {self.tie_mode.get()}")
        L.append(wrap(TIE_HELP.get(self.tie_mode.get(), "")))
        L.append(f"Fallback dist: {self.tie_dist.get()} mm")
        if self.tie_mode.get() == TIE_SCOPED:
            pairs = self.tie_pairs.get().rstrip()
            L.append("Scoped pairs:")
            for ln in (pairs or "(empty)").splitlines():
                L.append(IND + ln)
        L.append("")

        L.append("-" * W)
        L.append("RAW SETTINGS SNAPSHOT (machine-readable, same data as run.json)")
        L.append("-" * W)
        for k, v in sorted(self._settings_snapshot().items()):
            L.append(f"{k} = {v}")
        L.append("=" * W)
        return "\n".join(L) + "\n"

    def _write_settings_txt(self, deck_dir, model_name):
        """Write the per-build settings report next to the decks."""
        path = os.path.join(deck_dir, f"{model_name}_settings.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._settings_report(model_name))
            self.log_msg(f"Settings report written: {path}")
        except Exception as e:
            self.log_msg(f"Could not write settings report: {e}")

    def _record_build(self, target_dir, model_name, deck_rel=None):
        """Append a settings snapshot to run.json after a successful build, and
        archive the .inp/.pmx into model/ if the run was created empty."""
        meta_path = os.path.join(target_dir, "run.json")
        if not os.path.isfile(meta_path):
            return  # building outside a managed run — nothing to record
        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
        except Exception:
            meta = {}
        inp = self.inp_path.get().strip()
        if inp and os.path.isfile(inp) and not meta.get("archived_inp"):
            model_dir = os.path.join(target_dir, "model")
            try:
                os.makedirs(model_dir, exist_ok=True)
                shutil.copy2(inp, model_dir)
                meta["source_inp"] = inp
                meta["archived_inp"] = os.path.basename(inp)
                meta["prepomax_version"] = self._parse_prepomax_version(inp)
                pmx = os.path.splitext(inp)[0] + ".pmx"
                if os.path.isfile(pmx):
                    shutil.copy2(pmx, model_dir)
                    meta["archived_pmx"] = os.path.basename(pmx)
            except Exception as e:
                self.log_msg(f"Run Manager: could not archive model at build time: {e}")
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "deck": deck_rel or f"{model_name}_0000.rad",
            "settings": self._settings_snapshot(),
        }
        if self.fail_model.get() == FAIL_TENS:
            try:
                et1, et2, note = self._resolve_tens_thresholds()
                entry["tensstrain_resolved"] = {
                    "eps_t1": et1, "eps_t2": et2,
                    "s_flag": self.ts_sflag.get(), "note": note,
                }
            except Exception:
                pass
        meta.setdefault("builds", []).append(entry)
        try:
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
            self.log_msg("Run Manager: build settings recorded in run.json.")
        except Exception as e:
            self.log_msg(f"Run Manager: could not update run.json: {e}")

    def _run_list(self):
        """Run folders of the project dir, newest first: [{"name", "path", "builds", "prepomax_version",
        "description", "decks": [deck paths], "inp": archived .inp}]. Replaces the Tk list of _refresh_runs."""
        out = []
        root = self._runs_root()
        if not root or not os.path.isdir(root):
            return out
        for name in sorted(os.listdir(root), reverse=True):
            d = os.path.join(root, name)
            if not os.path.isdir(d):
                continue
            meta = {}
            try:
                with open(os.path.join(d, "run.json"), "r") as f:
                    meta = json.load(f)
            except Exception:
                pass
            decks = (glob.glob(os.path.join(d, "*_0000.rad")) +
                     glob.glob(os.path.join(d, "*", "*_0000.rad")))

            def _bnum(p):
                m = re.search(r"_b(\d+)_0000\.rad$", os.path.basename(p))
                return int(m.group(1)) if m else 0
            decks.sort(key=lambda p: (_bnum(p), os.path.basename(p)))
            inps = sorted(glob.glob(os.path.join(d, "model", "*.inp")))
            out.append({"name": name, "path": d.replace("\\", "/"), "builds": len(meta.get("builds", []) or []),
                        "prepomax_version": meta.get("prepomax_version"), "description": meta.get("description", ""),
                        "notes": meta.get("notes", ""), "created": meta.get("created", ""),
                        "decks": [p.replace("\\", "/") for p in decks],
                        "inp": inps[0].replace("\\", "/") if inps else ""})
        return out

    def _clean_victims(self, d):
        """Regenerable solver output of a run (cmd_clean_run without the dialog): (paths, MB, {folder: count})."""
        victims = []
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x.lower() != "model"]
            for name in files:
                if self._is_purgeable(name):
                    victims.append(os.path.join(root, name))
        size = 0.0
        for p in victims:
            try:
                size += os.path.getsize(p)
            except Exception:
                pass
        per_dir = {}
        for p in victims:
            rel = os.path.relpath(os.path.dirname(p), d)
            per_dir[rel if rel != "." else "(run root)"] = per_dir.get(rel if rel != "." else "(run root)", 0) + 1
        return victims, size / 1e6, per_dir

    def cmd_clean_run(self, d):
        """Delete the regenerable solver output of run folder d (the confirmation is asked by the web client)."""
        victims, size, per_dir = self._clean_victims(d)
        if not victims:
            self.log_msg("Run Manager: nothing to clean - no regenerable output found "
                         "anywhere in this run."); return 0
        n = 0
        for p in victims:
            try:
                os.remove(p); n += 1
            except Exception as e:
                self.log_msg(f"Run Manager: could not delete {os.path.relpath(p, d)}: {e}")
        self.log_msg(f"Run Manager: deleted {n} file(s) across {len(per_dir)} folder(s), "
                     f"freed {size:.1f} MB in {os.path.basename(d)}.")
        return n

    def cmd_list_parts(self):
        """Log 'PID: name' for every /PART in the Target .rad (or the newest deck
        in Output Dir) - reference for the Scoped Ties and Rigid Part fields,
        without having to provoke a no-match warning to see the list."""
        deck = self.rad_target.get().strip()
        if not deck or not os.path.isfile(deck):
            od = self.out_dir.get().strip()
            cand = sorted(glob.glob(os.path.join(od, "*_0000.rad"))) if od and os.path.isdir(od) else []
            deck = cand[-1] if cand else ""
        if not deck or not os.path.isfile(deck):
            self.log_msg("List Parts: no built deck found - BUILD once, then list parts.")
            return
        try:
            with open(deck, "r", errors="ignore") as fh:
                dlines = fh.readlines()
        except Exception as e:
            self.log_msg(f"List Parts: could not read {deck}: {e}")
            return
        self.log_msg(f"Parts in {os.path.basename(deck)}:")
        found = 0
        for i, l in enumerate(dlines):
            if l.strip().upper().startswith("/PART/"):
                try:
                    pid = int(l.strip().split("/")[2])
                except Exception:
                    continue
                name = dlines[i + 1].strip() if i + 1 < len(dlines) else ""
                self.log_msg(f"  {pid}: {name}")
                found += 1
        if not found:
            self.log_msg("  (no /PART cards found)")


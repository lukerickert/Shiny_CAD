"""Post-processing of the explicit analysis (ORC**3 workspace_post.py): anim->vtk, pvbatch/ParaView rendering,
principal strain extraction, KE/IE curves and salvage.

PostMixin of the headless workspace (host.Workspace)."""

import os
import json
import subprocess
import threading
import glob
import re
from datetime import datetime
from .constants import (NO_WINDOW)
from .scripts import (_EPS1_PF_SCRIPT, _EXTRACTOR_SCRIPT, _PV_MACRO_SCRIPT, _PV_SESSION_SCRIPT)


class PostMixin:
    def _read_anim_freq(self, run_folder, jobname):
        """Return (Tstart, Tfreq) from the engine deck's /ANIM/DT card; fallback (0.0, 1.0)."""
        try:
            with open(os.path.join(run_folder, f"{jobname}_0001.rad"), "r", errors="ignore") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if line.strip().upper().startswith("/ANIM/DT"):
                    for j in range(i + 1, len(lines)):
                        s = lines[j].strip()
                        if not s or s.startswith("#"):
                            continue
                        parts = s.replace(",", " ").split()
                        return float(parts[0]), float(parts[1])
        except Exception:
            pass
        return 0.0, 1.0

    def _write_vtk_series(self, run_folder, jobname, frames):
        """Emit <jobname>.vtk.series so the frames open as one time-grouped
        dataset in ParaView, independent of filename auto-detection."""
        if not frames:
            return
        try:
            frames = sorted(frames, key=lambda x: x[0])
            t0, dt = self._read_anim_freq(run_folder, jobname)
            # A001 is the t = Tstart state; frame n is at Tstart + (n-1)*dt
            entries = [{"name": name, "time": t0 + (n - 1) * dt} for n, name in frames]
            series_path = os.path.join(run_folder, f"{jobname}.vtk.series")
            with open(series_path, "w") as f:
                json.dump({"file-series-version": "1.0", "files": entries}, f, indent=2)
            self.log_msg(f"> ParaView series written: {series_path}")
            self.log_msg(f">   Open '{jobname}.vtk.series' in ParaView for the grouped animation.")
        except Exception as e:
            self.log_msg(f"> Could not write .vtk.series metafile: {e}")

    def _find_pvbatch(self):
        """Locate ParaView's pvbatch.exe (has vtk+numpy). Saved path wins; else
        probe common install locations."""
        p = self.pvbatch_path.get().strip()
        if p and os.path.isfile(p):
            return p
        cands = []
        cands += glob.glob(r"C:\Program Files\ParaView*\bin\pvbatch.exe")
        cands += glob.glob(os.path.expanduser(r"~\Documents\ParaView*\bin\pvbatch.exe"))
        cands += glob.glob(r"C:\ParaView*\bin\pvbatch.exe")
        for c in cands:
            if os.path.isfile(c):
                self.pvbatch_path.set(c)
                return c
        return None

    # ------------------------------------------------------------------
    # ParaView repeatable post-processing (v20.50)
    # ------------------------------------------------------------------
    def _parse_deck_tensstrain(self, run_folder, jobname):
        """Read the FIRST /FAIL/TENSSTRAIN card back out of the starter deck:
        (eps_t1, eps_t2, s_flag) or (None, None, None). The deck is the source
        of truth - it reflects what the solver actually used, including the
        v20.45 fallback resolution, and works for decks this GUI didn't build."""
        try:
            with open(os.path.join(run_folder, f"{jobname}_0000.rad"), "r", errors="ignore") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if line.strip().upper().startswith("/FAIL/TENSSTRAIN"):
                    for j in range(i + 1, len(lines)):
                        s = lines[j].strip()
                        if not s or s.startswith("#"):
                            continue
                        parts = s.split()
                        et1 = float(parts[0]) if len(parts) > 0 else None
                        et2 = float(parts[1]) if len(parts) > 1 else None
                        sflag = int(float(parts[5])) if len(parts) > 5 else None
                        return et1, et2, sflag
        except Exception:
            pass
        return None, None, None

    def _harvest_rigid_pids(self, run_folder, jobname):
        """Rigid-body identity for ParaView, read back from the starter deck so
        the session can (a) show the rigid structure as a grey backdrop and
        (b) spare it from the erosion filter (a rigid shell carries
        EROSION_STATUS=0 and is otherwise culled - the 'invisible impactor').

        Returns a dict: {"pids": [...], "nodes": [...]}.

        A rigid body's grnd_ID (main-line field 6) can point at EITHER:
          - /GRNOD/PART/<id>  -> the body lists part IDs directly  -> pids
          - /GRNOD/NODE/<id>  -> the body lists node IDs (PrePoMax rigid bodies
            do this: 'Internal_Selection..' node groups) -> nodes
        We harvest whichever it is. Node IDs are the robust key because they
        survive even a stripped deck with no element connectivity, and let the
        session protect the impactor by node membership without a PID lookup.
        Also still reads _gen_rigidify's 'Rigidify_' /GRNOD/PART groups.
        """
        pids, nodes = [], []
        path = os.path.join(run_folder, f"{jobname}_0000.rad")
        try:
            with open(path, "r", errors="ignore") as fh:
                lines = fh.read().splitlines()
        except Exception:
            return {"pids": pids, "nodes": nodes}

        def _body_ints(header_prefix, gid):
            """Integers listed in the /GRNOD/<KIND>/<gid> block body."""
            out, i = [], 0
            tag = f"{header_prefix}/{gid}"
            while i < len(lines):
                st = lines[i].strip()
                if st == tag or st.startswith(tag + " "):
                    j = i + 2  # skip keyword + title
                    while j < len(lines):
                        s = lines[j].strip()
                        if not s or s.startswith("#"):
                            j += 1; continue
                        if s.startswith("/"):
                            break
                        for tok in s.split():
                            try:
                                out.append(int(tok))
                            except ValueError:
                                pass
                        j += 1
                    break
                i += 1
            return out

        i = 0
        while i < len(lines):
            s = lines[i].strip()
            # _gen_rigidify part groups (verbatim)
            if s.startswith("/GRNOD/PART/"):
                title = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if title.startswith("Rigidify_"):
                    j = i + 2
                    while j < len(lines):
                        t = lines[j].strip()
                        if not t or t.startswith("#"):
                            j += 1; continue
                        if t.startswith("/"):
                            break
                        for tok in t.split():
                            try:
                                pids.append(int(tok))
                            except ValueError:
                                pass
                        j += 1
                    i = j; continue
            # any /RBODY -> follow grnd_ID to a PART group (pids) or NODE group (nodes)
            if s.startswith("/RBODY/"):
                k = i + 2
                while k < len(lines) and (not lines[k].strip()
                                          or lines[k].lstrip().startswith("#")):
                    k += 1
                fields = lines[k].split() if k < len(lines) else []
                if len(fields) >= 6:
                    try:
                        gid = int(fields[5])
                    except ValueError:
                        gid = 0
                    if gid > 0:
                        part_hits = _body_ints("/GRNOD/PART", gid)
                        if part_hits:
                            pids.extend(part_hits)
                        else:
                            nodes.extend(_body_ints("/GRNOD/NODE", gid))
            i += 1
        return {"pids": sorted(set(pids)), "nodes": sorted(set(nodes))}

    def _write_pv_manifest(self, run_folder, jobname):
        """Write <job>_pv.json: everything the ParaView session/renders need,
        harvested from the deck and the filename - never hand-typed."""
        et1, et2, sflag = self._parse_deck_tensstrain(run_folder, jobname)
        tm_ = re.search(r"_t(\d+(?:\.\d+)?)", jobname, re.I)
        mm_ = re.search(r"_m(\d+(?:\.\d+)?)", jobname, re.I)
        manifest = {
            "job": jobname,
            "series": f"{jobname}.vtk.series",
            "written": datetime.now().isoformat(timespec="seconds"),
            "eps_t1": et1, "eps_t2": et2, "s_flag": sflag,
            "thickness_mm": float(tm_.group(1)) if tm_ else None,
            "mesh_mm": float(mm_.group(1)) if mm_ else None,
            "screen_range": [0.0, 0.02],
            # v20.72 failure-centric colouring: with a /FAIL/TENSSTRAIN card in
            # the deck the session scales the LUT 0..rupture strain (lut_max =
            # EPSILON_T2, falling back to EPSILON_T1) so red = about to erode.
            # No failure card -> "c208" keeps the locked 0-0.02 screening band.
            # Both keys are plain JSON: hand-edit to force a mode or range.
            "color_mode": ("failure" if (et2 or et1) else "c208"),
            "lut_max": (et2 or et1),
            "erosion_keep_min": 0.5,
            "rigid_context": self._harvest_rigid_pids(run_folder, jobname),
            "show_rigid_context": True,
            "tstop": self._read_tstop(run_folder, jobname),
            "eps1_definition": "max principal TOTAL strain (eigenvalue of full 3x3 shell strain tensor)",
        }
        path = os.path.join(run_folder, f"{jobname}_pv.json")
        try:
            with open(path, "w") as f:
                json.dump(manifest, f, indent=2)
            return path
        except Exception as e:
            self.log_msg(f"> PV manifest error: {e}")
            return None

    def _write_pv_script(self, run_folder, jobname):
        """Write the per-run <job>_pv.py session script next to the results."""
        path = os.path.join(run_folder, f"{jobname}_pv.py")
        try:
            body = _PV_SESSION_SCRIPT.replace("__EPS1__", _EPS1_PF_SCRIPT).replace("__JOB__", jobname)
            with open(path, "w") as f:
                f.write(body)
            return path
        except Exception as e:
            self.log_msg(f"> PV script error: {e}")
            return None

    def _write_pv_assets(self, run_folder, jobname):
        """Manifest + session script, (re)generated together so the pair is
        always consistent. Cheap - runs after every job and salvage."""
        m = self._write_pv_manifest(run_folder, jobname)
        s = self._write_pv_script(run_folder, jobname)
        if m and s:
            self.log_msg(f"> ParaView session written: {os.path.basename(s)} "
                         f"(+ {os.path.basename(m)}) - 'Open in ParaView' or "
                         f"paraview --script={os.path.basename(s)}")

    def _render_pv_images(self, run_folder, jobname, force=False):
        """Standard deliverable PNG set via pvbatch: one render per eps1 field
        the filter produced (eps1_solid on solid decks; membrane/upper/lower on
        shells) at the last frame + the peak-primary-field frame. LUT range per
        the manifest's color_mode: 0..rupture strain on failure decks, the
        locked 0-0.02 C208 screen otherwise. Skipped unless 'PV Images' is
        ticked (or force)."""
        if not force and not self.pv_images.get():
            return
        pvb = self._find_pvbatch()
        if not pvb:
            self.log_msg("> PV images skipped: pvbatch.exe not found (set it via the 'Extract Strains' button).")
            return
        script = os.path.join(run_folder, f"{jobname}_pv.py")
        if not os.path.isfile(script):
            self._write_pv_assets(run_folder, jobname)
        if not os.path.isfile(script):
            return
        self.log_msg("> Rendering deliverable PV images (last frame x3 positions + peak frame) ...")
        try:
            env = os.environ.copy()
            env["PV_RENDER_PNGS"] = "1"
            proc = subprocess.run([pvb, script], cwd=run_folder, env=env,
                                  capture_output=True, text=True, timeout=1800,
                                  creationflags=NO_WINDOW)
            for ln in (proc.stdout or "").splitlines():
                if ln.strip():
                    self.log_msg(f"  {ln}")
            err = (proc.stderr or "").strip()
            if err:
                self.log_msg(f"  [pvbatch stderr] {err[:600]}")
        except subprocess.TimeoutExpired:
            self.log_msg("> PV images: pvbatch timed out after 30 min - renders incomplete.")
        except Exception as e:
            self.log_msg(f"> PV images error: {e}")

    def _find_paraview(self):
        """Locate paraview.exe. Saved path wins; else the sibling of pvbatch;
        else probe the usual install locations."""
        p = self.paraview_path.get().strip()
        if p and os.path.isfile(p):
            return p
        pvb = self._find_pvbatch()
        if pvb:
            cand = os.path.join(os.path.dirname(pvb), "paraview.exe")
            if os.path.isfile(cand):
                self.paraview_path.set(cand)
                return cand
        cands = []
        cands += glob.glob(r"C:\Program Files\ParaView*\bin\paraview.exe")
        cands += glob.glob(os.path.expanduser(r"~\Documents\ParaView*\bin\paraview.exe"))
        cands += glob.glob(r"C:\ParaView*\bin\paraview.exe")
        for c in cands:
            if os.path.isfile(c):
                self.paraview_path.set(c)
                return c
        return None

    def cmd_open_paraview(self, jobname, run_folder):
        """Open the per-run ParaView session: (re)generate the manifest+script
        from the deck on disk (so a re-calibrated rebuild is picked up), then
        launch paraview --script=<job>_pv.py."""
        if not jobname:
            return
        if not run_folder or not os.path.isdir(run_folder):
            self.log_msg(f"Open in ParaView: run folder not found: {run_folder}")
            return
        if not os.path.isfile(os.path.join(run_folder, f"{jobname}.vtk.series")):
            self.log_msg(f"Open in ParaView: no {jobname}.vtk.series in the folder - "
                         "run the job first (or 'Salvage Results' for a killed one).")
            return
        pv = self._find_paraview()
        if not pv:
            self.log_msg("Open in ParaView: paraview.exe not found - set ParaView (paraview.exe) in the Solve settings.")
            return
        self._write_pv_assets(run_folder, jobname)
        script = os.path.join(run_folder, f"{jobname}_pv.py")
        try:
            subprocess.Popen([pv, f"--script={script}"], cwd=run_folder, creationflags=NO_WINDOW)
            self.log_msg(f"ParaView launched with the {jobname} session.")
        except Exception as e:
            self.log_msg(f"Open in ParaView failed: {e}")

    def cmd_install_pv_macro(self):
        """Install the eps1 failure-view macro into ParaView's Macros folder so
        any interactive session gets the filter (shells AND solids), the
        erosion hide, and best-field colouring in one click. v20.72: renamed
        Eps1_C208 -> Eps1_View; an old Eps1_C208.py is removed on install so
        the two don't coexist in the toolbar."""
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        macro_dir = os.path.join(base, "ParaView", "Macros")
        try:
            os.makedirs(macro_dir, exist_ok=True)
            path = os.path.join(macro_dir, "Eps1_View.py")
            with open(path, "w") as f:
                f.write(_PV_MACRO_SCRIPT.replace("__EPS1__", _EPS1_PF_SCRIPT))
            old = os.path.join(macro_dir, "Eps1_C208.py")
            if os.path.isfile(old):
                try:
                    os.remove(old)
                    self.log_msg("  (superseded Eps1_C208.py removed)")
                except Exception:
                    pass
            self.log_msg(f"PV macro installed: {path}")
            self.log_msg("  It appears in ParaView's Macros menu/toolbar after a restart "
                         "(or immediately via Macros > Import new macro...). Select a loaded "
                         "source, click Eps1_View, done.")
        except Exception as e:
            self.log_msg(f"PV macro install failed: {e}")

    def _extract_principal_strains(self, run_folder, force=False):
        """Run the embedded principal-strain extractor via pvbatch over run_folder,
        writing principal_strains_summary.csv. Skipped unless enabled (or force)."""
        if not force and not self.extract_strains.get():
            return
        pvb = self._find_pvbatch()
        if not pvb:
            self.log_msg("> Strain extraction skipped: pvbatch.exe not found. "
                         "Use the 'Extract Strains' button to locate ParaView, or untick Extract Strains.")
            return
        try:
            script_path = os.path.join(run_folder, "_extract_principal_strain.py")
            with open(script_path, "w") as f:
                f.write(_EXTRACTOR_SCRIPT)
            self.log_msg("> Extracting principal strains (eps_1) via pvbatch ...")
            proc = subprocess.run([pvb, script_path, run_folder],
                                  capture_output=True, text=True, creationflags=NO_WINDOW)
            for ln in (proc.stdout or "").splitlines():
                self.log_msg(f"  {ln}")
            err = (proc.stderr or "").strip()
            if err:
                self.log_msg(f"  [pvbatch stderr] {err[:600]}")
            csv_out = os.path.join(run_folder, "principal_strains_summary.csv")
            if os.path.isfile(csv_out):
                self.log_msg(f"> Principal-strain summary written: {csv_out}")
        except Exception as e:
            self.log_msg(f"> Strain extraction error: {e}")

    def cmd_extract_strains(self, folder):
        """Extract principal strains from a results folder (recurses to find every .vtk.series), independent of
        solving. Runs in this thread."""
        if not folder or not os.path.isdir(folder):
            self.log_msg(f"> Extraction: results folder not found: {folder}")
            return
        if not self._find_pvbatch():
            self.log_msg("> Extraction cancelled: pvbatch.exe not set (Solve settings, pvbatch).")
            return
        self._extract_principal_strains(folder, True)

    def cmd_salvage(self, jobname, run_folder):
        """Salvage partial results from a killed / crashed job: convert whatever
        A-files and T01 exist (tolerating a corrupt final frame), rebuild the
        .vtk.series and _Results.csv, then plot KE and (checkbox permitting)
        extract strains. Target = the job and run folder chosen in the web client."""
        if not jobname:
            return
        if not run_folder or not os.path.isdir(run_folder):
            self.log_msg(f"Salvage: run folder not found: {run_folder}")
            return
        self.log_msg(f"\n--- SALVAGING RESULTS: {jobname} ---")
        threading.Thread(target=self._salvage_thread, args=(jobname, run_folder), daemon=True).start()

    def _salvage_thread(self, jobname, run_folder):
        try:
            remote = self.run_target.get() == "Remote (Linux)"
            transfer = remote and self._map_to_linux(run_folder) is None
            if transfer:
                # SCP-mode job: partial results live in the scratch workdir on
                # the server. Convert THERE (A-files never cross the wire),
                # then copy the .vtk/CSV/out set back as after a clean finish.
                workdir = self._remote_workdir(run_folder, jobname)
                self.log_msg(f"> Salvage: converting on the server in {workdir} ...")
                env = self._remote_env_prefix()
                ex = self.remote_exec.get().strip().rstrip("/")
                payload = (
                    f"for f in {jobname}A[0-9]*; do suff=$(echo $f | sed \'s/{jobname}A//\'); {ex}/anim_to_vtk_linux64_gf $f > {jobname}_$suff.vtk; done; "
                    f"{ex}/th_to_csv_linux64_gf {jobname}T01 > \"{jobname}_Results.csv\"; true"
                )
                cmd = self._ssh_base() + [f"cd '{workdir}' && {env}sh -c '{payload}'"]
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, creationflags=NO_WINDOW)
                    tail = ((r.stdout or "") + (r.stderr or "")).strip()
                    if tail:
                        for l in tail.splitlines()[-6:]:
                            self.log_msg(f"  {l}")
                    if r.returncode != 0:
                        self.log_msg(f"> Salvage: server conversion exit {r.returncode} - fetching whatever exists.")
                except subprocess.TimeoutExpired:
                    self.log_msg("> Salvage: server conversion timed out - fetching whatever exists.")
                self._fetch_remote_results(jobname, workdir, run_folder)
            else:
                # Local run, or a remote share-mode run: the A-files/T01 are in
                # (or visible at) run_folder, so convert with the local tools.
                anim_files = sorted(glob.glob(os.path.join(run_folder, f"{jobname}A[0-9]*")))
                if anim_files:
                    ok = bad = skipped = 0
                    for anim_file in anim_files:
                        base = os.path.basename(anim_file)
                        m = re.search(r"A(\d+)$", base)
                        out_name = f"{jobname}_{m.group(1)}.vtk" if m else f"{base}.vtk"
                        out_path = os.path.join(run_folder, out_name)
                        if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                            skipped += 1
                            continue
                        try:
                            with open(out_path, "wb") as out:
                                p = subprocess.run([self._or_exe("anim_to_vtk"), base], cwd=run_folder,
                                                   stdout=out, creationflags=NO_WINDOW, env=self._or_env())
                            # Reject anything that is not clean ASCII VTK (bad header /
                            # UTF-16 BOM) so it cannot pollute the .vtk.series.
                            _hdr_ok = False
                            if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                                with open(out_path, "rb") as _vf:
                                    _hdr_ok = (_vf.read(5) == b"# vtk")
                            if p.returncode == 0 and _hdr_ok:
                                ok += 1
                            else:
                                if os.path.isfile(out_path) and not _hdr_ok:
                                    self.log_msg(f"> Salvage: {out_name} had a bad VTK header "
                                                 f"(encoding/BOM) - discarded.")
                                bad += 1
                        except FileNotFoundError:
                            self.log_msg("> Salvage: anim_to_vtk_win64 not found on PATH - skipping VTK conversion.")
                            break
                        except Exception:
                            bad += 1
                        finally:
                            # A failed converter leaves the redirect's empty
                            # .vtk behind - remove it so it cannot pollute the
                            # frames glob / .vtk.series below.
                            try:
                                if os.path.isfile(out_path) and os.path.getsize(out_path) == 0:
                                    os.remove(out_path)
                            except Exception:
                                pass
                    msg = f"> Salvage: {ok} frame(s) converted, {skipped} already present"
                    if bad:
                        msg += f", {bad} unreadable (a frame being written at the kill is expected to be corrupt)"
                    self.log_msg(msg + ".")
                else:
                    self.log_msg("> Salvage: no A-files found - the job may have died before the first /ANIM/DT interval.")

                try:
                    csv_proc = subprocess.run([self._or_exe("th_to_csv"), f"{jobname}T01"], cwd=run_folder,
                                              capture_output=True, text=True, creationflags=NO_WINDOW,
                                              env=self._or_env())
                    self._finalize_results_csv(run_folder, jobname, csv_proc.stdout)
                except FileNotFoundError:
                    self.log_msg("> Salvage: th_to_csv_win64 not found on PATH - no Results CSV; the KE plot needs it.")
                except Exception as e:
                    self.log_msg(f"> Salvage: th_to_csv failed: {e}")

            # Series metafile over whatever frames survived (overwrites so late
            # partial salvages pick up every frame present now).
            frames = []
            for vf in glob.glob(os.path.join(run_folder, f"{jobname}_*.vtk")):
                m3 = re.search(r"_(\d+)\.vtk$", os.path.basename(vf))
                if m3 and os.path.getsize(vf) > 0:
                    frames.append((int(m3.group(1)), os.path.basename(vf)))
            if frames:
                self._write_vtk_series(run_folder, jobname, frames)

            if glob.glob(os.path.join(run_folder, f"{jobname}*.rst")):
                self.log_msg("> Salvage: restart (.rst) files exist - the run can also be RESUMED from the "
                             "last checkpoint with an _0002.rad engine deck instead of re-running from t=0.")

            if jobname in self.job_status:
                self._status_touch(jobname, note="salvaged (partial results)")
            self.log_msg(f"--- Salvage complete: {jobname} (results up to the kill point). ---")
            self._plot_ke(run_folder, jobname, force=True, select_tab=True)
            self._write_pv_assets(run_folder, jobname)
            self._extract_principal_strains(run_folder)
            self._render_pv_images(run_folder, jobname)
            if not self.extract_strains.get():
                self.log_msg("> Salvage: 'Extract Strains' is unticked - use the button if you want "
                             "principal strains from the salvaged frames.")
        except Exception as e:
            self.log_msg(f"Salvage Error [{jobname}]: {e}")

    def _plot_ke(self, run_folder, jobname, open_after=True, force=False, select_tab=False):
        """Parse <jobname>_Results.csv, save the KE PNG next to the results, and
        load the curve into the Results tab. Every exit path logs - a silently
        missing plot is a bug, not a behaviour. (open_after is retained for
        call compatibility; the external image viewer is no longer launched -
        the embedded Results tab replaces it.)"""
        if not force and not self.plot_ke.get():
            return
        csv_path, parsed = self._find_th_csv(run_folder, jobname)
        if not csv_path:
            named = os.path.join(run_folder, f"{jobname}_Results.csv")
            tfile = os.path.join(run_folder, f"{jobname}T01")
            if os.path.exists(named):
                hint = (" A _Results.csv exists but has no numeric rows (banner-only stdout capture) "
                        "and no converter-written <job>T01.csv with data was found either.")
            elif os.path.exists(tfile):
                hint = (" The T-file exists, so th_to_csv did not run or produced no output - "
                        "use the 'Plot KE' button to rebuild the CSV.")
            else:
                hint = " No T-file either - the engine may not have completed."
            self.log_msg(f"KE plot: no parseable results CSV for {jobname}.{hint}")
            return
        self.log_msg(f"KE plot: reading {os.path.basename(csv_path)} ...")
        t, ke, ie, note = parsed
        if note:
            self.log_msg(f"KE plot: {note}.")

        # Curve into the Results panel (host.Workspace.ke_curves)
        self._ke_add_curve(jobname, t, ke, ie, csv_path)

        # PNG export kept for the run folder record (Figure API - no pyplot,
        # safe from worker threads, no backend switching needed).
        try:
            from matplotlib.figure import Figure
        except Exception as e:
            self.log_msg(f"KE PNG skipped: matplotlib not available ({e}). Install with: pip install matplotlib")
            return
        try:
            fig = Figure(figsize=(8, 4.5))
            ax = fig.add_subplot(111)
            ax.plot(t, ke, color="#111111", lw=1.6)
            ax.set_xlabel("Time"); ax.set_ylabel("Kinetic Energy")
            ax.set_title(f"{jobname} - Kinetic Energy")
            ax.grid(True, alpha=0.3); fig.tight_layout()
            png = os.path.join(run_folder, f"{jobname}_KE.png")
            fig.savefig(png, dpi=120)
            self.log_msg(f"KE plot saved: {png}  (peak KE = {max(ke):.4g}) - curve shown in the Results tab.")
        except Exception as e:
            self.log_msg(f"KE plot error: {e}")


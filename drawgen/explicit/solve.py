"""Solver submission of the explicit analysis (ORC**3 workspace_solve.py): local and remote (ssh/tsp) job execution,
the run queue and the job status records.

SolveMixin of the headless workspace (host.Workspace). The status board is self.job_status / self.job_order; the
web client reads it (host.Workspace.status)."""

import os
import shutil
import subprocess
import threading
import glob
import re

from .constants import (NO_WINDOW, _FAIL_MARKERS, _KILL_RE, _MSGID_RE, _NC_RE, _TIME_RE, _fort_float)


# Terminal statuses recorded into the Run History (Solve tab).
_HISTORY_TERMINAL = ("Done", "Failed", "Killed", "Starter done")


class SolveMixin:
    def _resolve_run_sources(self, env_label):
        """v20.66: decide what Run launches, loudly. Rules:
        - queue empty            -> the selected Target .rad
        - Target empty           -> the queue
        - Target IS in the queue -> the queue (classic batch: Add Current, Run)
        - Target NOT in queue    -> the TARGET ONLY; the queue is kept intact.
          (Previously the queue silently hijacked Run, so a deck queued for
          one environment made it impossible to run a different deck on the
          other. The queue is never modified here.)"""
        single = self.rad_target.get().strip()
        if not self.job_queue:
            if not single:
                self.log_msg("Error: No target .rad file selected and the queue is empty.")
                return None
            return [single]
        if not single:
            self.log_msg(f"{env_label}: running the {len(self.job_queue)}-deck queue (no Target selected).")
            return list(self.job_queue)
        if single in self.job_queue:
            self.log_msg(f"{env_label}: Target is in the queue - running the whole "
                         f"{len(self.job_queue)}-deck queue.")
            return list(self.job_queue)
        self.log_msg(f"{env_label}: running the SELECTED Target only "
                     f"('{os.path.basename(single)}'); the {len(self.job_queue)}-deck "
                     f"queue is left intact (add the Target to the queue if you wanted a batch).")
        return [single]

    def _env_busy_acquire(self, env):
        """True if acquired. Refuses only when the SAME environment is already
        running - the other environment stays free (local + remote in parallel)."""
        if env in self._busy_envs:
            self.log_msg(f"Error: a {env} batch is already running. Kill it or wait for it "
                         f"to finish. (The other environment is still available.)")
            return False
        self._busy_envs.add(env)
        return True

    def _env_busy_release(self, env):
        self._busy_envs.discard(env)

    def _status_reset_for(self, launch_jobnames, missing):
        """Refresh the status board for a new batch WITHOUT wiping live rows
        that belong to the other environment's running batch (v20.66; the old
        wholesale clear() erased a streaming remote job's row the moment a
        local run started, and vice versa). Finished rows are dropped; live
        rows not in this batch are kept."""
        for jn in list(self.job_order):
            st = (self.job_status.get(jn) or {}).get("status", "")
            if jn in launch_jobnames or st in ("Done", "Failed", "Killed", "Skipped", "Starter done"):
                self.job_status.pop(jn, None)
                try: self.job_order.remove(jn)
                except ValueError: pass
        for jobname, run_folder in missing:
            self._status_touch(jobname, status="Failed", note="deck file not found on disk")

    def cmd_run(self):
        if self.run_target.get() == "Local (Windows)":
            self._kickoff_local("run")
        else:
            self._kickoff_ssh("run")

    def cmd_run_starter(self):
        """Run ONLY the starter (no engine, no post) so its /DT/NODA/CST
        added-mass table is produced; the local path then offers a Min dt for
        the current target DM/M. Remote runs the starter on the server and
        streams its output - read the table from the fetched _0000.out or via
        the Suggest Min dt button."""
        if self.run_target.get() == "Local (Windows)":
            self._kickoff_local("starter")
        else:
            self._kickoff_ssh("starter")

    def cmd_kill(self):
        if self.run_target.get() == "Local (Windows)":
            self.log_msg("\nSending kill signal to local OpenRadioss processes...")
            self.local_abort = True
            try:
                if os.name == "nt":
                    subprocess.Popen("taskkill /F /IM starter_win64.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
                    subprocess.Popen("taskkill /F /IM engine_win64.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
                lp = getattr(self, "_local_proc", None)
                if lp is not None and lp.poll() is None:
                    lp.kill()
                self.log_msg("Local kill signal dispatched.")
            except Exception as e:
                self.log_msg(f"Local Kill Error: {e}")
        else:
            # Kill the RUNNING solver AND drop the tsp queue - previously only
            # the running processes were pkilled, so the next queued tsp job
            # would immediately start. tsp -K kills the spooler server itself
            # (queued jobs vanish; the next tsp call restarts it empty).
            self.log_msg("\nKilling remote OpenRadioss processes and flushing the tsp queue...")
            self.remote_abort = True
            env = self._remote_env_prefix()
            cmd = self._ssh_base() + [f"{env}tsp -K 2>/dev/null; pkill -9 -f linux64_gf 2>/dev/null; echo killed"]
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
                self.log_msg("Kill signal dispatched (running job killed, queued tsp jobs dropped).")
            except Exception as e:
                self.log_msg(f"Kill Command Error: {e}")
            # Stop the local stream so the worker unblocks promptly.
            tp = getattr(self, "_remote_tail_proc", None)
            if tp is not None:
                try: tp.terminate()
                except Exception: pass
            # Board bookkeeping: running rows -> Killed, waiting rows -> Skipped.
            for jn, rec in self.job_status.items():
                st = (rec.get("status") or "").lower()
                if st in ("starter", "running", "post-processing", "starting engine"):
                    self._status_touch(jn, status="Killed")
                elif st == "queued":
                    self._status_touch(jn, status="Skipped")

    def _ssh_base(self):
        """Base ssh argv using the configured server and port (so off-network
        targets like a VPN/Tailscale IP or DDNS host work without code edits)."""
        port = self.ssh_port.get().strip() or "22"
        return ["ssh", "-p", port, self.ssh_host.get().strip()]

    def _scp_base(self):
        """scp counterpart of _ssh_base (scp uses -P, ssh uses -p)."""
        port = self.ssh_port.get().strip() or "22"
        return ["scp", "-P", port]

    def _remote_env_prefix(self):
        """'source <env script> && ' when one is configured, else ''. The env
        script is what puts tsp and the solver on PATH for non-login shells."""
        env = self.remote_env.get().strip()
        return f"source '{env}' && " if env else ""

    def _share_map_pairs(self):
        """Parse the Share map field into [(win_prefix, linux_prefix), ...].
        Pairs are 'WIN => LINUX', ';'-separated; slashes normalised, matching
        is case-insensitive on the Windows side."""
        pairs = []
        for chunk in self.share_map.get().split(";"):
            if "=>" not in chunk:
                continue
            w, l = chunk.split("=>", 1)
            w = w.strip().replace("\\", "/")
            l = l.strip().rstrip("/")
            if w and l:
                pairs.append((w, l))
        return pairs

    def _map_to_linux(self, win_path):
        """Translate a local folder to its server-side path via the Share map.
        Returns the Linux path, or None when the folder is not on any mapped
        share (caller falls back to SCP transfer mode)."""
        p = win_path.replace("\\", "/")
        for w, l in self._share_map_pairs():
            wn = w.rstrip("/")
            if p.upper() == wn.upper():
                return l
            if p.upper().startswith(wn.upper() + "/") or (w.endswith("/") and p.upper().startswith(w.upper())):
                rest = p[len(wn):].lstrip("/")
                return f"{l}/{rest}" if rest else l
        return None

    def cmd_shutdown(self):
        if True:   # confirmed by the web client
            self.log_msg(f"\nSending shutdown command to {self.ssh_host.get().strip()}...")
            cmd = self._ssh_base() + ["sudo shutdown -h now"]
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
                self.log_msg("Shutdown signal dispatched. Connection will be lost.")
            except Exception as e:
                self.log_msg(f"Shutdown Command Error: {e}")

    def _queue_add(self):
        fp = self.rad_target.get().strip()
        if not fp:
            self.log_msg("Queue: no Target .rad selected to add.")
            return
        if not fp.endswith("_0000.rad"):
            self.log_msg("Queue: pick the starter deck (..._0000.rad) before adding.")
            return
        self.job_queue.append(fp)
        self._queue_refresh()
        self.log_msg(f"Queue: added '{os.path.basename(fp)}' ({len(self.job_queue)} queued).")

    def _queue_clear(self):
        n_defs = len(self.job_queue)
        self.job_queue.clear()
        dropped, kept = [], []
        for jn in list(self.job_order):
            st = (self.job_status.get(jn) or {}).get("status", "")
            if st in ("Done", "Failed", "Killed", "Skipped", "Starter done") or (st == "Queued" and not self._status_ticker):
                self.job_status.pop(jn, None)
                self.job_order.remove(jn)
                dropped.append(jn)
            else:
                kept.append(f"{jn} ({st})")
        self._queue_refresh()
        msg = f"Queue: cleared - {n_defs} queued deck(s)"
        if dropped:
            msg += f", {len(dropped)} finished status row(s)"
        msg += " removed."
        if kept:
            msg += f" Kept live rows: {', '.join(kept)} (Kill to stop them)."
        self.log_msg(msg)

    # ------------------------------------------------------------------
    # Job Status board
    # ------------------------------------------------------------------
    def _status_touch(self, jobname, **kw):
        """Create/update a job record. Safe to call from worker threads: only
        the dict is mutated here; the Treeview is redrawn by _status_tick on
        the main thread."""
        rec = self.job_status.get(jobname)
        if rec is None:
            rec = {"status": "Queued", "nc": None, "t": None, "dt": None,
                   "tstop": None, "elapsed": None, "eta": None,
                   "err": None, "dmm": None, "note": ""}
            self.job_status[jobname] = rec
            self.job_order.append(jobname)
        # Run History: record the FIRST transition into a terminal status
        # (the same status touched twice, e.g. Kill from two paths, is not
        # recorded twice).
        new_st = kw.get("status")
        if new_st in _HISTORY_TERMINAL and rec.get("status") != new_st:
            snap = dict(rec)
            snap.update(kw)
            self._history_add(jobname, new_st,
                              self.job_folders.get(jobname, ""),
                              getattr(self, "job_envs", {}).get(jobname, ""),
                              err=snap.get("err"), dmm=snap.get("dmm"),
                              elapsed=snap.get("elapsed"), nc=snap.get("nc"))
        rec.update(kw)
        self._status_dirty = True

    def _find_th_csv(self, run_folder, jobname):
        """Locate a parseable time-history CSV for the job. th_to_csv builds
        differ: some print the table to stdout (captured into <job>_Results.csv),
        others write <job>T01.csv themselves and print only a banner. Try
        _Results.csv first, then converter-written candidates.
        Returns (csv_path, (t, ke, ie, note)) or (None, None)."""
        cands = [os.path.join(run_folder, f"{jobname}_Results.csv")]
        cands += sorted(glob.glob(os.path.join(run_folder, f"{jobname}T[0-9][0-9]*.csv")))
        seen = set()
        for cp in cands:
            if cp in seen or not os.path.isfile(cp):
                continue
            seen.add(cp)
            try:
                return cp, self._parse_th_csv(cp)
            except Exception:
                continue
        return None, None

    def _finalize_results_csv(self, run_folder, jobname, stdout_text):
        """Write <job>_Results.csv from th_to_csv stdout, validate it, and fall
        back to a converter-written <job>T01.csv when stdout was banner-only.
        stdout_text=None means 'validate whatever _Results.csv already exists
        in place' - the remote path, where the server wrote the file by shell
        redirect and there is no locally captured stdout.
        Returns True when a parseable _Results.csv is in place."""
        results_csv = os.path.join(run_folder, f"{jobname}_Results.csv")
        wrote = False
        if stdout_text is None:
            if os.path.isfile(results_csv):
                try:
                    self._parse_th_csv(results_csv)
                    return True
                except Exception:
                    wrote = True  # exists but banner-only: same fallback path as a bad capture
        elif (stdout_text or "").strip():
            with open(results_csv, "w") as out:
                out.write(stdout_text)
            wrote = True
        if wrote and stdout_text is not None:
            try:
                self._parse_th_csv(results_csv)
                return True
            except Exception:
                pass  # banner-only stdout - fall through to converter-written file
        alts = sorted(glob.glob(os.path.join(run_folder, f"{jobname}T[0-9][0-9]*.csv")))
        for a in alts:
            try:
                self._parse_th_csv(a)
            except Exception:
                continue
            shutil.copyfile(a, results_csv)
            self.log_msg(f"CSV: stdout had no data rows; this th_to_csv build writes the table itself - "
                         f"adopted {os.path.basename(a)} as {os.path.basename(results_csv)}.")
            return True
        if wrote:
            if stdout_text is None:
                try:
                    with open(results_csv, "r", errors="ignore") as fh:
                        first = (fh.read().strip().splitlines() or ["(empty)"])[0][:120]
                except Exception:
                    first = "(unreadable)"
            else:
                first = (stdout_text.strip().splitlines() or ["(empty)"])[0][:120]
            self.log_msg("CSV WARNING: captured output has no numeric rows and no converter-written "
                         f"CSV was found - the KE plot will fail. First captured line: {first}")
        else:
            self.log_msg("CSV WARNING: th_to_csv produced no output - no Results CSV written; "
                         "the KE plot will report the CSV as missing.")
        return False

    def _parse_th_csv(self, csv_path):
        """Parse a th_to_csv *_Results.csv into (t, ke, ie_or_None, note).
        Delimiter-agnostic per line (comma vs whitespace), tolerant of quoted /
        '#'-prefixed headers and title lines; raises ValueError with a short
        reason on failure. 'note' reports any fallback column guessing."""
        with open(csv_path, 'r', errors='ignore') as fh:
            raw = [line.rstrip("\n") for line in fh if line.strip()]
        if len(raw) < 2:
            raise ValueError("CSV has no data rows")

        def toks(line):
            s = line.strip().lstrip("#").strip()
            parts = s.split(",") if "," in s else s.split()
            return [p.strip().strip('"') for p in parts if p.strip().strip('"')]

        def numeric(parts):
            if len(parts) < 2:
                return None
            try:
                return [float(p) for p in parts]
            except Exception:
                return None

        first_data = None
        for i, line in enumerate(raw):
            if numeric(toks(line)) is not None:
                first_data = i; break
        if first_data is None:
            raise ValueError("no numeric data rows found (first line: %r)" % raw[0][:120])

        header = toks(raw[first_data - 1]) if first_data > 0 else []
        t_idx = 0
        for i, h in enumerate(header):
            if h.lower() == "time":
                t_idx = i; break
        ke_idx = ie_idx = None
        for i, h in enumerate(header):
            hu = h.upper()
            if ke_idx is None and "KINETIC" in hu: ke_idx = i
            if ie_idx is None and "INTERNAL" in hu: ie_idx = i

        data = [v for v in (numeric(toks(l)) for l in raw[first_data:]) if v]
        ncols = min(len(v) for v in data)
        note = ""
        if ke_idx is None or ke_idx >= ncols:
            ke_idx = 2 if ncols > 2 else ncols - 1
            note = (f"no 'KINETIC' column label matched - using column {ke_idx} "
                    f"(global TH order: time, internal energy, kinetic energy)")
        if ie_idx is not None and ie_idx >= ncols:
            ie_idx = None
        if ie_idx is None and ncols > 2 and ke_idx == 2:
            ie_idx = 1  # global TH default order
        if t_idx >= ncols:
            t_idx = 0

        need = max(t_idx, ke_idx, ie_idx if ie_idx is not None else 0)
        t  = [v[t_idx]  for v in data if len(v) > need]
        ke = [v[ke_idx] for v in data if len(v) > need]
        ie = [v[ie_idx] for v in data if len(v) > need] if ie_idx is not None else None
        if not t:
            raise ValueError("no numeric data parsed from CSV")
        return t, ke, ie, note

    def _read_tstop(self, run_folder, jobname):
        """Tstop from the /RUN card of the engine deck; GUI Tstop as fallback."""
        try:
            with open(os.path.join(run_folder, f"{jobname}_0001.rad"), "r", errors="ignore") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if line.strip().upper().startswith("/RUN"):
                    for j in range(i + 1, len(lines)):
                        s = lines[j].strip()
                        if not s or s.startswith("#"):
                            continue
                        return float(s.replace(",", " ").split()[0])
        except Exception:
            pass
        try:
            return float(self.tstop.get())
        except Exception:
            return None

    def _server_queue_show_thread(self):
        remote = (self._remote_env_prefix() +
                  "echo '== RUNNING SOLVER ==' && (pgrep -af linux64_gf || echo '(none running)') && "
                  "echo '== TSP QUEUE ==' && tsp")
        try:
            out = subprocess.run(self._ssh_base() + [remote], capture_output=True, text=True, timeout=25, creationflags=NO_WINDOW)
            text = (out.stdout or "") + (out.stderr or "")
            lines = [l.rstrip() for l in text.splitlines() if l.strip()] or ["(no response)"]
            import time as _t
            display = [f"Server status @ {_t.strftime('%H:%M:%S')}"] + lines
            self.server_queue = display
            self.log_msg("Server status shown in the queue box.")
        except subprocess.TimeoutExpired:
            self.log_msg("Server query timed out (check Tailscale/SSH).")
        except Exception as e:
            self.log_msg(f"Server query failed: {e}")

    def _server_queue_clear_thread(self):
        # tsp -K kills the spooler server itself so QUEUED jobs are dropped too
        # (tsp -k only killed the running one, letting the next queued job start).
        remote = (self._remote_env_prefix() +
                  "tsp -K 2>/dev/null; pkill -9 -f linux64_gf 2>/dev/null; echo cleared")
        try:
            subprocess.run(self._ssh_base() + [remote], capture_output=True, text=True, timeout=25, creationflags=NO_WINDOW)
            self.log_msg("Server queue cleared.")
        except Exception as e:
            self.log_msg(f"Clear server queue failed: {e}")
        self._server_queue_show_thread()  # refresh the display

    def _kickoff_ssh(self, mode):
        """Remote counterpart of _kickoff_local: runs the whole job queue (or
        the single Target .rad), initialises the status board, and hands the
        batch to a worker. Jobs on a mapped share run in place on the server;
        anything else is SCP'd to the scratch dir (streaming required so the
        results can be copied back on completion)."""
        self.save_state()
        sources = self._resolve_run_sources("Remote")
        if sources is None:
            return

        jobs, missing = [], []  # jobs: (jobname, run_folder_win, linux_dir_or_None)
        for fp in sources:
            fp = fp.strip()
            if not fp:
                continue
            run_folder = os.path.dirname(fp)
            jobname = os.path.basename(fp).replace("_0000.rad", "")
            if not os.path.isfile(fp):
                missing.append((jobname, run_folder))
                self.log_msg(f"Queue WARNING: deck not found on disk, job will be marked Failed: {fp}")
                continue
            jobs.append((jobname, run_folder, self._map_to_linux(run_folder)))

        if not jobs and not missing:
            self.log_msg("Error: No valid jobs to run.")
            return
        if not jobs:
            self.log_msg("Error: every queued deck is missing on disk - nothing to dispatch. "
                         "'Clear' the queue and re-add from existing builds.")
            return
        if not self.ssh_host.get().strip():
            self.log_msg("Error: Server (user@host) is empty.")
            return

        streaming = self.stream_remote.get()
        transfers = [j[0] for j in jobs if j[2] is None]
        if transfers and not streaming:
            self.log_msg(f"Error: {len(transfers)} job(s) are not on a mapped share ({', '.join(transfers)}) "
                         "and would use SCP transfer, which needs 'Stream remote output' ON so results can "
                         "be copied back when each job finishes. Enable streaming, or extend the Share map.")
            return

        if not self._env_busy_acquire("remote"):
            return
        cores = self.ssh_threads.get()
        self.remote_abort = False
        self.log_msg(f"\n--- INITIALIZING REMOTE EXECUTION: {len(jobs)} job(s) -> {self.ssh_host.get().strip()} ---")

        # Status board: reset only THIS batch's rows and drop finished ones;
        # a live local row keeps ticking (v20.66). Tstop comes off the LOCAL
        # copy of the engine deck, so remote progress is real T/Tstop too.
        self._status_reset_for({jn for jn, _rf, _l in jobs}, missing)
        self.job_envs = getattr(self, "job_envs", {})
        for jobname, run_folder, _lin in jobs:
            self.job_folders[jobname] = run_folder
            self.job_envs[jobname] = "remote"
            self._status_touch(jobname, status="Queued",
                               tstop=self._read_tstop(run_folder, jobname))
        self._refresh_status_tree()
        self._ticker_start()

        threading.Thread(target=self._exec_ssh_queue_thread, args=(jobs, cores, mode), daemon=True).start()

    def _exec_ssh_queue_thread(self, jobs, cores, mode):
        try:
            total = len(jobs)
            streaming = self.stream_remote.get()
            abort_logged = False
            for idx, (jobname, run_folder, linux_dir) in enumerate(jobs, 1):
                if self.remote_abort:
                    if not abort_logged:
                        self.log_msg("\n> Remote queue aborted by user; remaining jobs skipped.")
                        abort_logged = True
                    self._status_touch(jobname, status="Skipped")
                    continue
                if total > 1:
                    self.log_msg(f"\n=== REMOTE QUEUE JOB {idx} OF {total}: {jobname} ===")
                self._run_remote_job(jobname, run_folder, linux_dir, cores, mode, streaming)
            if total > 1 and not self.remote_abort:
                self.log_msg(f"\nRemote queue complete: {total} job(s) dispatched.")
        except Exception as e:
            self.log_msg(f"Remote Queue Error: {e}")
        finally:
            self._env_busy_release("remote")
            self.after(0, self._maybe_ticker_stop)

    def _remote_pipeline(self, jobname, cores, mode="run"):
        """The sh -c payload enqueued to tsp. mode='run' is the full pipeline:
        starter -> engine -> anim-to-vtk loop -> th_to_csv -> optional
        .vtk.series helper. mode='starter' runs ONLY the starter so its
        /DT/NODA/CST added-mass table is written, then stops. All paths come
        from the Solve tab fields; the payload sits inside single quotes so the
        remote shell does not expand $f/$suff at enqueue time (the escaped
        quotes around the sed program are the usual quote-out dance)."""
        ex = self.remote_exec.get().strip().rstrip("/")
        if mode == "starter":
            return f"{ex}/starter_linux64_gf -i {jobname}_0000.rad -np 1"
        try:
            n_frames = max(1, int(float(self.anim_frames.get())))
        except Exception:
            n_frames = 100
        try:
            anim_dt = float(self.tstop.get()) / n_frames
        except Exception:
            anim_dt = 0.001
        # write_series.py historically lives two levels above exec/
        # (<root>/OpenRadioss/exec -> <root>/write_series.py); a missing helper
        # is non-fatal - the GUI rebuilds the .vtk.series locally afterwards.
        helper = ex.rsplit("/", 2)[0] + "/write_series.py" if "/" in ex else "write_series.py"
        return (
            f"{ex}/starter_linux64_gf -i {jobname}_0000.rad -np 1 && "
            f"{ex}/engine_linux64_gf -i {jobname}_0001.rad -nt {cores} && "
            f"for f in {jobname}A[0-9]*; do suff=$(echo $f | sed \'s/{jobname}A//\'); {ex}/anim_to_vtk_linux64_gf $f > {jobname}_$suff.vtk; done && "
            f"{ex}/th_to_csv_linux64_gf {jobname}T01 > \"{jobname}_Results.csv\"; "
            f"if [ -f {helper} ]; then python3 {helper} {jobname} {anim_dt}; fi"
        )

    def _remote_workdir(self, run_folder, jobname):
        """Scratch workdir for SCP-transfer jobs. One place only, used by the
        runner AND salvage so they can never disagree. The folder-name
        component is sanitised to scp-safe characters (no spaces/quotes) -
        OpenSSH 9.x scp speaks SFTP by default, where the remote path is NOT
        shell-parsed and every character is literal."""
        scratch = self.remote_scratch.get().strip().rstrip("/") or "~/RADIOSS_RUNNING"
        leaf = os.path.basename(run_folder) or jobname
        leaf = re.sub(r"[^A-Za-z0-9._-]+", "_", leaf)
        return f"{scratch}/{leaf}"

    def _run_remote_job(self, jobname, run_folder, linux_dir, cores, mode, streaming):
        """Dispatch ONE job to the server's tsp queue and (when streaming)
        follow it to completion: live status parsing, copy-back for SCP-mode
        jobs, CSV validation, KE plot and strain extraction - the same tail
        the local runner has."""
        host = self.ssh_host.get().strip()
        env = self._remote_env_prefix()
        transfer = linux_dir is None
        try:
            if transfer:
                workdir = self._remote_workdir(run_folder, jobname)
                self.log_msg(f"> {jobname}: run folder is not on a mapped share - SCP transfer via {workdir}")
                mk = subprocess.run(self._ssh_base() + [f"mkdir -p '{workdir}'"],
                                    capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
                if mk.returncode != 0:
                    self._status_touch(jobname, status="Failed", note="mkdir failed on server")
                    self.log_msg(f"> {jobname}: FAILED - could not create {workdir}: {(mk.stderr or mk.stdout).strip()}")
                    return
                for fn in (f"{jobname}_0000.rad", f"{jobname}_0001.rad"):
                    lp = os.path.join(run_folder, fn)
                    if not os.path.isfile(lp):
                        self._status_touch(jobname, status="Failed", note=f"{fn} missing locally")
                        self.log_msg(f"> {jobname}: FAILED - {lp} not found.")
                        return
                    # NO quotes in the remote path: OpenSSH 9.x scp defaults to
                    # the SFTP protocol, which has no remote shell - embedded
                    # quotes become literal path characters and the copy fails.
                    up = subprocess.run(self._scp_base() + [lp, f"{host}:{workdir}/"],
                                        capture_output=True, text=True, timeout=300, creationflags=NO_WINDOW)
                    if up.returncode != 0:
                        self._status_touch(jobname, status="Failed", note=f"scp {fn} failed")
                        self.log_msg(f"> {jobname}: FAILED - scp of {fn}: {(up.stderr or up.stdout).strip()}")
                        return
                self.log_msg(f"> {jobname}: decks uploaded.")
            else:
                workdir = linux_dir

            cmd = self._ssh_base() + [f"cd '{workdir}' && {env}tsp sh -c '{self._remote_pipeline(jobname, cores, mode)}'"]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, creationflags=NO_WINDOW)
            jobid = None
            for line in iter(process.stdout.readline, ''):
                if not line:
                    continue
                s = line.strip()
                self.log_msg(f"> {s}")
                if s.isdigit():
                    jobid = s   # tsp prints the new job id when it enqueues
            process.wait()
            if process.returncode not in (0, None) or jobid is None:
                self._status_touch(jobname, status="Failed", note="tsp enqueue failed")
                self.log_msg(f"> {jobname}: FAILED to enqueue (ssh exit {process.returncode}, tsp id {jobid}). "
                             "Check host, env script and that task-spooler (tsp) is installed.")
                return
            self.log_msg(f"Job {jobname} dispatched to remote queue (tsp id {jobid}).")
            self._status_touch(jobname, status="Queued", note=f"tsp {jobid}")

            if not streaming:
                self.log_msg(f"Streaming off: no live status or post-processing for {jobname} - "
                             "check with 'Show Queue'; results appear on the share when tsp finishes it.")
                return

            self.log_msg(f"--- Live output for tsp job {jobid} (the job keeps running on the server even if this stream drops) ---")
            fail_marker = None
            self._status_touch(jobname, status="Starter")
            tail_cmd = self._ssh_base() + [f"{env}tsp -t {jobid}"]
            tproc = subprocess.Popen(tail_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, creationflags=NO_WINDOW)
            self._remote_tail_proc = tproc
            try:
                for line in iter(tproc.stdout.readline, ''):
                    if not line:
                        continue
                    s = line.strip()
                    self.log_msg(f"  {s}")
                    m = _NC_RE.search(s)
                    if m:
                        # _fort_float repairs the E-less overflow exponent
                        # ('1.6791+256') the solver prints on the final cycle
                        # before a mass-error kill; a bad line must never abort
                        # the whole console read.
                        try:
                            self._status_touch(jobname, status="Running",
                                               nc=int(m.group(1)),
                                               t=_fort_float(m.group(2)),
                                               dt=_fort_float(m.group(3)),
                                               err=_fort_float(m.group(4)),
                                               dmm=_fort_float(m.group(5)))
                        except ValueError:
                            self.log_msg(f"  (unparseable cycle line kept as text: {s[:80]})")
                    else:
                        m2 = _TIME_RE.search(s)
                        if m2:
                            self._status_touch(jobname,
                                               elapsed=float(m2.group(1)),
                                               eta=float(m2.group(2)))
                        elif fail_marker is None:
                            mk_kill = _KILL_RE.search(s)
                            mk_msg = _MSGID_RE.search(s)
                            if mk_kill:
                                reason = (mk_kill.group(1) or "").strip() or "RUN KILLED"
                                fail_marker = f"RUN KILLED: {reason}"[:120]
                            elif mk_msg:
                                fail_marker = f"MESSAGE ID {mk_msg.group(1)}"[:120]
                            else:
                                su = s.upper()
                                for mk_ in _FAIL_MARKERS:
                                    if mk_ in su:
                                        fail_marker = s[:120]
                                        break
                tproc.wait()
            finally:
                self._remote_tail_proc = None

            if self.remote_abort:
                self._status_touch(jobname, status="Killed")
                self.log_msg(f"> {jobname}: killed by user.")
                return
            if fail_marker:
                self._status_touch(jobname, status="Failed", note=fail_marker)
                self.log_msg(f"> {jobname}: FAILED on server - {fail_marker}")
                if transfer:
                    self._fetch_remote_results(jobname, workdir, run_folder, outs_only=True)
                self.log_msg(f">   See the {jobname}_0000/0001.out listings in the run folder.")
                return

            if mode == "starter":
                # Starter-only remote pass: bring back the .out (with the
                # /DT/NODA/CST table) for SCP jobs, then offer the Min dt. No
                # engine, no post-processing.
                self._status_touch(jobname, status="Starter done", eta=None)
                if transfer:
                    self._fetch_remote_results(jobname, workdir, run_folder, outs_only=True)
                out_path = os.path.join(run_folder, f"{jobname}_0000.out")
                self.log_msg(f"> {jobname}: remote starter-only pass complete.")
                self._offer_min_dt_from_out(out_path, jobname)
                return

            self._status_touch(jobname, status="Post-processing", eta=None)
            if transfer:
                self._fetch_remote_results(jobname, workdir, run_folder)
            # Rebuild the ParaView series locally if the server helper was
            # missing (or the fetch skipped it) - frames are on disk either way.
            if not os.path.isfile(os.path.join(run_folder, f"{jobname}.vtk.series")):
                frames = []
                for vf in glob.glob(os.path.join(run_folder, f"{jobname}_*.vtk")):
                    m3 = re.search(r"_(\d+)\.vtk$", os.path.basename(vf))
                    if m3 and os.path.getsize(vf) > 0:
                        frames.append((int(m3.group(1)), os.path.basename(vf)))
                if frames:
                    self._write_vtk_series(run_folder, jobname, frames)

            # v20.44 CSV fix, remote edition: the server wrote _Results.csv by
            # redirect - validate it in place and adopt the converter-written
            # T01.csv when it is banner-only.
            self._finalize_results_csv(run_folder, jobname, None)

            self.log_msg(f"--- Remote job {jobname} finished. Open {jobname}.vtk.series in ParaView. ---")
            self._plot_ke(run_folder, jobname)
            self._write_pv_assets(run_folder, jobname)
            self._extract_principal_strains(run_folder)
            self._render_pv_images(run_folder, jobname)
            self._status_touch(jobname, status="Done", eta=None)
        except Exception as e:
            self._status_touch(jobname, status="Failed", note=str(e)[:120])
            self.log_msg(f"SSH Execution Error [{jobname}]: {e}")

    def _fetch_remote_results(self, jobname, workdir, run_folder, outs_only=False):
        """SCP-mode copy-back: pull the job's results from the scratch workdir
        into the local run folder. A-files stay on the server - the .vtk
        frames are what ParaView (and the strain extractor) consume."""
        host = self.ssh_host.get().strip()
        patterns = [f"{jobname}_[0-9]*.out"]
        if not outs_only:
            patterns = [f"{jobname}_[0-9]*.vtk", f"{jobname}.vtk.series",
                        f"{jobname}T01*", f"{jobname}_Results.csv"] + patterns
        self.log_msg(f"> {jobname}: copying results back from {workdir} ...")
        got = 0
        for pat in patterns:
            cmd = self._scp_base() + [f"{host}:{workdir}/{pat}", run_folder]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, creationflags=NO_WINDOW)
                if r.returncode == 0:
                    got += 1
            except Exception as e:
                self.log_msg(f"> {jobname}: copy-back of {pat} failed: {e}")
        if got:
            self.log_msg(f"> {jobname}: results copied to {run_folder} (A-files left on the server).")
        else:
            self.log_msg(f"> {jobname}: WARNING - nothing copied back from {workdir}; "
                         "check the tsp output above and the workdir contents on the server.")

    def _kickoff_local(self, mode="run"):
        self.save_state()
        sources = self._resolve_run_sources("Local")
        if sources is None:
            return

        jobs, missing = [], []
        for fp in sources:
            fp = fp.strip()
            if not fp:
                continue
            run_folder = os.path.dirname(fp)
            jobname = os.path.basename(fp).replace("_0000.rad", "")
            if not os.path.isfile(fp):
                # Stale queue entry (build folder deleted/renamed): fail it on
                # the board up front instead of letting the starter die with a
                # cryptic 'INPUT FILE NOT FOUND' listing.
                missing.append((jobname, run_folder))
                self.log_msg(f"Queue WARNING: deck not found on disk, job will be marked Failed: {fp}")
                continue
            jobs.append((jobname, run_folder))

        if not jobs and not missing:
            self.log_msg("Error: No valid jobs to run.")
            return
        if not jobs:
            self.log_msg("Error: every queued deck is missing on disk - nothing to run. "
                         "'Clear List' the queue and re-add from existing builds.")
            return
        if not self._env_busy_acquire("local"):
            return

        cores = self.ssh_threads.get()
        self.local_abort = False
        self.log_msg(f"\n--- INITIALIZING LOCAL EXECUTION: {len(jobs)} job(s) queued ---")

        # Status board: reset only THIS batch's rows and drop finished ones;
        # a live remote row keeps ticking (v20.66).
        self._status_reset_for({jn for jn, _rf in jobs}, missing)
        self.job_envs = getattr(self, "job_envs", {})
        for jobname, run_folder in jobs:
            self.job_folders[jobname] = run_folder
            self.job_envs[jobname] = "local"
            self._status_touch(jobname, status="Queued",
                               tstop=self._read_tstop(run_folder, jobname))
        self._refresh_status_tree()
        self._ticker_start()

        threading.Thread(target=self._exec_local_thread, args=(jobs, cores, mode), daemon=True).start()

    def _exec_local_thread(self, jobs, cores, mode):
        try:
            total = len(jobs)
            abort_logged = False
            for idx, (jobname, run_folder) in enumerate(jobs, 1):
                if self.local_abort:
                    if not abort_logged:
                        self.log_msg("\n> Queue aborted by user; remaining jobs skipped.")
                        abort_logged = True
                    self._status_touch(jobname, status="Skipped")
                    continue
                if total > 1:
                    self.log_msg(f"\n=== QUEUE JOB {idx} OF {total}: {jobname} ===")
                self._run_local_job(jobname, run_folder, cores, mode)
            if total > 1 and not self.local_abort:
                self.log_msg(f"\nQueue complete: {total} job(s) finished.")
        except Exception as e:
            self.log_msg(f"Local Queue Error: {e}")
        finally:
            self._env_busy_release("local")
            self.after(0, self._maybe_ticker_stop)

    def _run_local_job(self, jobname, run_folder, cores, mode):
        try:
            starter_only = (mode == "starter")
            cmds = [
                [self._or_exe("starter"), "-i", f"{jobname}_0000.rad", "-np", "1"],
                [self._or_exe("engine"), "-i", f"{jobname}_0001.rad", "-nt", str(cores)]
            ]
            if starter_only:
                # v20.67: starter-only pass - run just the starter so its
                # /DT/NODA/CST added-mass table is written, then stop. No engine,
                # no post-processing. Used to pick Min dt before the real run.
                cmds = cmds[:1]
                self.log_msg(f"> {jobname}: STARTER-ONLY pass (no engine, no post-processing).")
            for cmd in cmds:
                if self.local_abort:
                    self._status_touch(jobname, status="Killed")
                    return
                phase = "Starter" if os.path.basename(cmd[0]).startswith("starter") else "Running"
                self._status_touch(jobname, status=phase if phase == "Starter" else "Starting engine")
                fail_marker = None
                self.log_msg(f"> Running: {' '.join(cmd)}")
                process = subprocess.Popen(cmd, cwd=run_folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=NO_WINDOW, env=self._or_env())
                self._local_proc = process
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        continue
                    s = line.strip()
                    self.log_msg(f"> {s}")
                    # Live status: cycle lines carry T/DT/ERR/DM/M, the
                    # elapsed lines carry the solver's own ETA.
                    m = _NC_RE.search(s)
                    if m:
                        # _fort_float repairs the E-less overflow exponent
                        # ('1.6791+256') printed on the last cycle before a
                        # mass-error kill; before v20.67 this ValueError aborted
                        # the local read and surfaced as a bare Python message
                        # instead of the real "TOTAL MASS ERROR" diagnosis.
                        try:
                            self._status_touch(jobname, status="Running",
                                               nc=int(m.group(1)),
                                               t=_fort_float(m.group(2)),
                                               dt=_fort_float(m.group(3)),
                                               err=_fort_float(m.group(4)),
                                               dmm=_fort_float(m.group(5)))
                        except ValueError:
                            self.log_msg(f"> (unparseable cycle line kept as text: {s[:80]})")
                    else:
                        m2 = _TIME_RE.search(s)
                        if m2:
                            self._status_touch(jobname,
                                               elapsed=float(m2.group(1)),
                                               eta=float(m2.group(2)))
                        elif fail_marker is None:
                            mk_kill = _KILL_RE.search(s)
                            mk_msg = _MSGID_RE.search(s)
                            if mk_kill:
                                reason = (mk_kill.group(1) or "").strip() or "RUN KILLED"
                                fail_marker = f"RUN KILLED: {reason}"[:120]
                            elif mk_msg:
                                fail_marker = f"MESSAGE ID {mk_msg.group(1)}"[:120]
                            else:
                                su = s.upper()
                                for mk in _FAIL_MARKERS:
                                    if mk in su:
                                        fail_marker = s[:120]
                                        break
                process.wait()

                try:
                    i_idx = cmd.index('-i'); rad_file = cmd[i_idx + 1]
                except ValueError:
                    rad_file = f"{jobname}_0000.rad"
                out_file = os.path.join(run_folder, rad_file.replace('.rad', '.out'))
                if os.path.exists(out_file):
                    with open(out_file, 'r', errors='ignore') as f:
                        for line in f:
                            if line.strip(): self.log_msg(f"> {line.strip()}")

                if self.local_abort:
                    self._status_touch(jobname, status="Killed")
                    self.log_msg(f"> {jobname}: killed by user during {cmd[0]}.")
                    return
                if process.returncode not in (0, None) or fail_marker:
                    reason = fail_marker or f"{cmd[0]} exit code {process.returncode}"
                    self._status_touch(jobname, status="Failed", note=reason)
                    self.log_msg(f"> {jobname}: FAILED in {cmd[0]} - {reason}")
                    self.log_msg(f">   See {out_file} for the full listing.")
                    return

            if starter_only:
                # Starter finished cleanly and no engine follows. Read the
                # /DT/NODA/CST added-mass table straight from the starter .out
                # and offer the Min dt for the current target - no file dialog.
                self._status_touch(jobname, status="Starter done", eta=None)
                self.log_msg(f"> {jobname}: starter-only pass complete.")
                self._offer_min_dt_from_out(os.path.join(run_folder, f"{jobname}_0000.out"), jobname)
                return

            self._status_touch(jobname, status="Post-processing", eta=None)
            self.log_msg("> Directing Fallback Layout: Translating Animation Decks to Sequential .vtk...")
            try:
                anim_files = glob.glob(os.path.join(run_folder, f"{jobname}A[0-9]*"))
                if anim_files:
                    anim_list = [os.path.basename(f) for f in anim_files]
                    frames = []  # (step_int, out_name)
                    for anim_file in anim_list:
                        match = re.search(r'A(\d+)$', anim_file)
                        if match:
                            step_num = match.group(1)
                            out_name = f"{jobname}_{step_num}.vtk"
                            step_int = int(step_num)
                        else:
                            out_name = f"{anim_file}.vtk"
                            step_int = None

                        # Binary mode: subprocess writes the tool's raw bytes to the
                        # fd. Text mode would still be byte-clean here (the child
                        # bypasses Python's encoder), but "wb" states the intent and
                        # rules out any newline/encoding translation on a refactor.
                        out_path = os.path.join(run_folder, out_name)
                        with open(out_path, "wb") as out:
                            subprocess.run([self._or_exe("anim_to_vtk"), anim_file], cwd=run_folder, stdout=out, creationflags=NO_WINDOW, env=self._or_env())

                        # Valid legacy VTK starts with "# vtk". Anything else (e.g. a
                        # UTF-16 BOM 0xFF 0xFE from a shell '>' redirect) makes
                        # ParaView reject the file with "no reader found". Catch it at
                        # write time, name the cause, and drop the file so it cannot
                        # poison the .vtk.series.
                        with open(out_path, "rb") as _vf:
                            if _vf.read(5) != b"# vtk":
                                self.log_msg(f"> VTK WARNING: {out_name} has a bad header - not clean "
                                             f"ASCII VTK (likely encoding/BOM). Removing it; do not "
                                             f"convert with a PowerShell '>' redirect.")
                                try: os.remove(out_path)
                                except Exception: pass
                                continue

                        if step_int is not None:
                            frames.append((step_int, out_name))

                    # Declare the series explicitly so ParaView groups the frames
                    self._write_vtk_series(run_folder, jobname, frames)
                else:
                    self.log_msg("> No animation files found for conversion.")
            except FileNotFoundError:
                self.log_msg("> VTK WARNING: anim_to_vtk_win64 not found on PATH - skipping VTK conversion. "
                             "CSV export, KE plot and strain extraction continue.")
            except Exception as e:
                self.log_msg(f"> VTK conversion error: {e} - continuing with CSV export.")

            self.log_msg("> Exporting Time History to CSV...")
            try:
                csv_cmd = [self._or_exe("th_to_csv"), f"{jobname}T01"]
                csv_proc = subprocess.run(csv_cmd, cwd=run_folder, capture_output=True, text=True, creationflags=NO_WINDOW, env=self._or_env())

                if csv_proc.stderr:
                    self.log_msg(f"CSV Log: {csv_proc.stderr.strip()}")

                self._finalize_results_csv(run_folder, jobname, csv_proc.stdout)
            except FileNotFoundError:
                self.log_msg("CSV WARNING: th_to_csv_win64 not found on PATH - no Results CSV; "
                             "the KE plot needs it. Add the OpenRadioss exec folder to PATH.")
            except Exception as e:
                self.log_msg(f"CSV export error: {e}")

            self.log_msg(f"Local Task Complete: {jobname}")
            self.log_msg(f"Data exported to: {os.path.join(run_folder, f'{jobname}_Results.csv')}")
            self._plot_ke(run_folder, jobname)
            self._write_pv_assets(run_folder, jobname)
            self._extract_principal_strains(run_folder)
            self._render_pv_images(run_folder, jobname)
            self._status_touch(jobname, status="Done", eta=None)
        except Exception as e:
            self._status_touch(jobname, status="Failed", note=str(e)[:120])
            self.log_msg(f"Local Execution Error [{jobname}]: {e}")

    def _queue_remove(self, key):
        """Remove a queued deck ("q::<path>") or a finished status row ("s::<job>") (ORC**3: the selected row)."""
        iid = key or ""
        if iid.startswith("q::"):
            fp = iid[3:]
            if fp in self.job_queue:
                self.job_queue.remove(fp)
                self.log_msg(f"Queue: removed '{os.path.basename(fp)}'.")
            self._queue_refresh()
            return
        if iid.startswith("s::"):
            jn = iid[3:]
            st = (self.job_status.get(jn) or {}).get("status", "")
            terminal = st in ("Done", "Failed", "Killed", "Skipped", "Starter done")
            idle_queued = (st == "Queued" and not self._busy_envs)
            if terminal or idle_queued:
                self.job_status.pop(jn, None)
                if jn in self.job_order:
                    self.job_order.remove(jn)
                self.log_msg(f"Queue: dropped status row '{jn}' ({st}).")
                self._queue_refresh()
            elif st == "Queued":
                self.log_msg(f"Queue: '{jn}' is pending in the RUNNING batch - Kill the batch to skip it.")
            else:
                self.log_msg(f"Queue: '{jn}' is {st} - Kill it before removing its row.")
            return
        self.log_msg("Queue: select a queued deck or a finished status row to remove.")

    def _queue_refresh(self):
        self.save_state()

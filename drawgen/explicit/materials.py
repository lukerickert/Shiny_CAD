"""Material, failure and timestep cards of the explicit analysis (ORC**3 workspace_materials.py): /MAT, /FAIL and
/FUNCT generators, the load-hold-unload curve, the Min dt advisor and the shell normal healing.

MaterialsMixin of the headless workspace (host.Workspace)."""

import os
import math
import re
from .constants import (FAIL_JC, FAIL_TENS)


class MaterialsMixin:
    def _lhu_ease(self, u, shape):
        """Easing s(u), u in [0,1], s(0)=0, s(1)=1, for the LHU profile."""
        u = min(1.0, max(0.0, u))
        if shape == "Linear":
            return u
        if shape == "Cosine":
            return 0.5 * (1.0 - math.cos(math.pi * u))
        if shape == "Smoothstep":
            return u * u * (3.0 - 2.0 * u)
        return u * u * u * (u * (u * 6.0 - 15.0) + 10.0)   # Smootherstep (quintic)

    def _build_lhu_curve(self, ramp_up, hold, ramp_down, settle, shape, n_ramp):
        """(times, values) for 0 -> 1 (ramp_up) -> hold -> 0 (ramp_down) ->
        settle at 0. Values are the normalized 0..1 shape; the actual peak
        displacement is applied as the /IMPDISP Fscale. Ramps get n_ramp points,
        holds their two ends. Raises ValueError on a zero ramp (an impulse)."""
        if ramp_up <= 0 or ramp_down <= 0:
            raise ValueError("ramp-up and ramp-down must be > 0 (a zero ramp is a shock).")
        if min(hold, settle) < 0:
            raise ValueError("hold and settle must be >= 0.")
        n_ramp = max(2, int(n_ramp))
        t0 = 0.0; t1 = ramp_up; t2 = t1 + hold; t3 = t2 + ramp_down; t4 = t3 + settle
        ts, vs = [], []
        def push(t, v):
            if ts and abs(t - ts[-1]) < 1e-15:
                vs[-1] = v; return
            ts.append(t); vs.append(v)
        for k in range(n_ramp):
            u = k / (n_ramp - 1)
            push(t0 + u * ramp_up, self._lhu_ease(u, shape))
        if hold > 0:
            push(t2, 1.0)
        for k in range(n_ramp):
            u = k / (n_ramp - 1)
            push(t2 + u * ramp_down, 1.0 - self._lhu_ease(u, shape))
        if settle > 0:
            push(t4, 0.0)
        return ts, vs

    def _lib_rate_table(self, data):
        """Rate table for a LAW36 library entry: list of (eps_dot, DIF scale).
        Slot 1 is ALWAYS the unscaled static curve at rate 0 (the deck-writer's
        Eps_dot_1=0 patch relies on this). Cowper-Symonds scaling
        DIF = 1 + (rate/D)^(1/q) is applied to the further slots when the
        entry carries cs_D/cs_q/rates; otherwise one static curve only."""
        table = [(0.0, 1.0)]
        D, q = data.get("cs_D", 0.0), data.get("cs_q", 0.0)
        rates = data.get("rates", [])
        if D > 0.0 and q > 0.0 and rates:
            for r in sorted(rates)[:4]:      # 5 LAW36 slots total incl. static
                table.append((float(r), 1.0 + (float(r) / D) ** (1.0 / q)))
        return table

    def _gen_law36(self, mat_id, name, data, func_id):
        """PLAS_TAB card. func_id is the base function ID; rate-dependent
        entries use consecutive IDs func_id, func_id+1, ... (one per curve),
        matching the /FUNCT blocks emitted by the caller via _gen_funct."""
        table = self._lib_rate_table(data)
        n = len(table)
        rate_dep = n > 1
        # Rate lookup smoothing: without a cutoff the per-cycle strain-rate
        # signal chatters between curves; Fsmooth=1 + F_cut=1e4 /s is the
        # standard remedy.
        fsmooth = 1 if rate_dep else 0
        fcut = 1.0e4 if rate_dep else 0.0
        ids_row = "".join(f"{func_id + k:>10}" for k in range(n)) + "\n"
        fscale_row = "".join(f"{0.0:>20.1f}" for _ in range(n)) + "\n"
        rate_row = "".join(f"{r:>20.4f}" for r, _s in table) + "\n"
        return [
            f"/MAT/PLAS_TAB/{mat_id}\n", f"{name}\n", "#              RHO_I\n", f"{data['rho']:>20.5e}{0:>10}\n",
            "#                  E                  nu           Eps_p_max               Eps_t               Eps_m\n",
            f"{data['E']:>20.1f}{data['nu']:>20.4f}{0.0:>20.4f}{0.0:>20.4f}{0.0:>20.4f}\n",
            "#  N_funct  F_smooth              C_hard               F_cut               Eps_f                  VP\n",
            f"{n:>10}{fsmooth:>10}{0.0:>20.1f}{fcut:>20.1f}{0.0:>20.1f}{0:>10}\n",
            "#  fct_IDp              Fscale   Fct_IDE                EInf                  CE\n",
            f"{0:>10}{0.0:>20.1f}{0:>10}{0.0:>20.1f}{0.0:>20.1f}\n",
            "# func_ID1  func_ID2  func_ID3  func_ID4  func_ID5\n", ids_row,
            "#           Fscale_1            Fscale_2            Fscale_3            Fscale_4            Fscale_5\n",
            fscale_row,
            "#          Eps_dot_1           Eps_dot_2           Eps_dot_3           Eps_dot_4           Eps_dot_5\n",
            rate_row
        ]

    def _gen_law2(self, mat_id, name, data):
        """PLAS_JOHNS (Johnson-Cook) card, Iflag=0 analytic input:
        sigma = (a + b*eps_p^n) * (1 + c*ln(epsdot/eps0)). Rate smoothing
        (Fsmooth=1, F_cut=1e4) is enabled whenever c > 0. Thermal row zeroed
        (no softening). Eps_p_max / Sig_max0 left 0 - failure comes from the
        Failure section (/FAIL card or the kept-material Eps_max patch)."""
        c = data.get("c", 0.0)
        eps0 = data.get("eps0", 1.0)
        fsmooth = 1 if c > 0.0 else 0
        fcut = 1.0e4 if c > 0.0 else 0.0
        return [
            f"/MAT/PLAS_JOHNS/{mat_id}\n", f"{name}\n",
            "#              RHO_I\n", f"{data['rho']:>20.5e}\n",
            "#                  E                  Nu     Iflag\n",
            f"{data['E']:>20.1f}{data['nu']:>20.4f}{0:>10}\n",
            "#                  a                   b                   n           Eps_p_max            Sig_max0\n",
            f"{data['a']:>20.4f}{data['b']:>20.4f}{data['n']:>20.4f}{0.0:>20.4f}{0.0:>20.4f}\n",
            "#                  c           Eps_dot_0       ICC   Fsmooth               F_cut               Chard\n",
            f"{c:>20.6f}{eps0:>20.6f}{0:>10}{fsmooth:>10}{fcut:>20.1f}{0.0:>20.1f}\n",
            "#                  m              T_melt              rhoC_p                 T_r\n",
            f"{0.0:>20.1f}{0.0:>20.1f}{0.0:>20.1f}{0.0:>20.1f}\n"
        ]

    def _gen_law1(self, mat_id, name, data):
        """LAW1 (ELAST) linear elastic card - indenters / tooling / supports."""
        return [
            f"/MAT/LAW1/{mat_id}\n", f"{name}\n",
            "#              RHO_I\n", f"{data['rho']:>20.5e}\n",
            "#                  E                  Nu\n",
            f"{data['E']:>20.1f}{data['nu']:>20.4f}\n"
        ]

    def _scan_inivel_targets(self, lines):
        """Resolve every /INIVEL/TRA in a deck to (node_set, (vx,vy,vz), label).

        /INIVEL/TRA targets a GRNOD (Gnod_id in col 4), so this first builds a
        map of /GRNOD/NODE/<id> -> {node ids}, then reads each INIVEL's velocity
        line and target group. Returns a list of dicts. Used by the pre-flight
        duplicate-velocity guard: two INIVELs that resolve to the SAME node with
        DIFFERENT velocities is a silent last-write-wins trap (the 14 vs 15 m/s
        case) that must halt the build, not warn-and-continue.

        Only /GRNOD/NODE is resolved (the common impactor case). INIVELs whose
        group is some other GRNOD flavour are returned with an empty node set and
        skipped by the guard rather than guessed at.
        """
        def _is_num(tok):
            try:
                float(tok); return True
            except ValueError:
                return False

        grnod_nodes = {}   # gid -> set(node ids)
        i, n = 0, len(lines)
        while i < n:
            up = lines[i].strip().upper()
            if up.startswith("/GRNOD/NODE/"):
                try:
                    gid = int(up.rsplit("/", 1)[1])
                except ValueError:
                    i += 1; continue
                nodes = set()
                j = i + 1
                # The line right after the header is the group title (skip it);
                # every subsequent non-comment, all-integer line is node IDs.
                title_skipped = False
                while j < n:
                    t = lines[j].strip()
                    if t.startswith("/"):
                        break
                    if not t or t.startswith("#"):
                        j += 1; continue
                    if not title_skipped:
                        title_skipped = True
                        # A title is non-numeric; if this first payload line is
                        # already numeric, there was no title - fall through.
                        if not _is_num(t.split()[0]):
                            j += 1; continue
                    for tok in t.split():
                        if tok.lstrip("-").isdigit():
                            nodes.add(int(tok))
                    j += 1
                grnod_nodes.setdefault(gid, set()).update(nodes)
                i = j; continue
            i += 1

        inivels = []
        i = 0
        while i < n:
            up = lines[i].strip().upper()
            if up.startswith("/INIVEL/TRA/"):
                iid = up.rsplit("/", 1)[1] if "/" in up else "?"
                vx = vy = vz = 0.0
                gid = None
                # The velocity data line is the first non-comment line whose
                # first whitespace token is numeric (the title line is text).
                j = i + 1
                while j < n:
                    t = lines[j].strip()
                    if t.startswith("/"):
                        break
                    if not t or t.startswith("#"):
                        j += 1; continue
                    toks = t.split()
                    if not _is_num(toks[0]):
                        j += 1; continue          # title line
                    try:
                        if len(toks) >= 3:
                            vx, vy, vz = float(toks[0]), float(toks[1]), float(toks[2])
                        if len(toks) >= 4:
                            gid = int(float(toks[3]))
                    except ValueError:
                        pass
                    break
                node_set = grnod_nodes.get(gid, set()) if gid is not None else set()
                inivels.append({"id": iid, "gid": gid, "vel": (vx, vy, vz),
                                "nodes": node_set})
                i += 1; continue
            i += 1
        return inivels

    def _erosion_active(self):
        """True when the current failure model can DELETE elements during the run.

        This is the condition that makes contact Idel matter: once elements
        erode, a TYPE7/19/24 interface with Idel=0 keeps dead segments on the
        main side and orphaned nodes on the secondary side. A node that loses
        every connected element then has no element mass or stiffness, and
        /DT/NODA/CST tries to hold the timestep by scaling its mass -> runaway
        added mass -> MESSAGE ID 207, TOTAL MASS ERROR (the 72% blow-up).

        - Johnson-Cook and Max-principal write dedicated /FAIL/ cards that
          delete elements: always erosive.
        - Equivalent plastic strain deletes only if a nonzero limit is set;
          empty/0 = Eps_max stays 0 = no deletion.
        """
        fm = self.fail_model.get()
        if fm in (FAIL_JC, FAIL_TENS):
            return True
        s = (self.fail_strain.get() or "").strip()
        try:
            return float(s) > 0.0
        except ValueError:
            return False

    def _parse_added_mass_table(self, text):
        """Parse the starter's '/DT/NODA/CST' added-mass estimation from a
        _0000.out listing. The starter prints, once, two things we use:

          NODAL TIME STEP DISTRIBUTION ... <smallest natural nodal dt> ... <largest>
          INITIAL ADDED MASS ESTIMATION for /DT/NODA/CST
              DM/M at first cycle | Target time step @0.9 | Target time step @0.67
                 1.000E-02        |     4.417E-06         |     3.288E-06
                 ...

        Returns {'floor_dt': float|None, 'rows': [{'dmm','dt_09','dt_067'}, ...]}.
        An empty 'rows' means the table was not found (starter aborted before it,
        or /DT/NODA/CST is not the timestep control) - the caller says so plainly
        rather than guessing.
        """
        out = {"floor_dt": None, "rows": []}
        lines = text.splitlines()

        # Natural nodal-timestep floor: the LEFT value on the axis line beneath
        # the 'NODAL TIME STEP DISTRIBUTION' histogram. Below this Min dt, the
        # solver adds NO mass (every node already clears the floor).
        for i, ln in enumerate(lines):
            if "NODAL TIME STEP DISTRIBUTION" in ln:
                for j in range(i, min(i + 45, len(lines))):
                    if "-->" in lines[j] and "NODAL TIME STEP" in lines[j]:
                        for k in range(j + 1, min(j + 4, len(lines))):
                            nums = re.findall(r"\d+\.\d+E[+-]\d+", lines[k])
                            if len(nums) >= 2:
                                try:
                                    out["floor_dt"] = float(nums[0])
                                except ValueError:
                                    pass
                                break
                        break
                break

        # The numeric estimation table: rows 'DMM | dt@0.9 | dt@0.67' after the
        # 'DM/M at first cycle ... Target time step' header, up to the WARNING.
        hdr = None
        for i, ln in enumerate(lines):
            if "DM/M at first cycle" in ln and "Target time step" in ln:
                hdr = i
                break
        if hdr is not None:
            for ln in lines[hdr + 1:]:
                if "WARNING" in ln.upper():
                    break
                if ln.count("|") >= 2:
                    nums = re.findall(r"[-+]?\d*\.?\d+E[+-]\d+", ln)
                    if len(nums) >= 3:
                        try:
                            out["rows"].append({"dmm": float(nums[0]),
                                                "dt_09": float(nums[1]),
                                                "dt_067": float(nums[2])})
                        except ValueError:
                            pass
        return out

    def _recommend_min_dt(self, parsed, target_dmm, scale="0.9"):
        """Interpolate the parsed table to a Min dt for a target first-cycle
        DM/M (fraction, e.g. 0.02 = 2%). Linear between rows, clamped at the
        table ends. Returns (dt|None, note). The deck writes /DT/NODA/CST with
        scale 0.9, so that is the default column."""
        rows = sorted(parsed.get("rows", []), key=lambda r: r["dmm"])
        if not rows:
            return None, "no /DT/NODA/CST added-mass table in that output file"
        key = "dt_09" if str(scale).startswith("0.9") else "dt_067"
        lo, hi = rows[0], rows[-1]
        if target_dmm <= lo["dmm"]:
            return lo[key], (f"target {target_dmm*100:g}% is at/below the table minimum "
                             f"{lo['dmm']*100:g}% - using the smallest tabulated dt")
        if target_dmm >= hi["dmm"]:
            return hi[key], (f"target {target_dmm*100:g}% is at/above the table maximum "
                             f"{hi['dmm']*100:g}% - using the largest tabulated dt")
        for a, b in zip(rows, rows[1:]):
            if a["dmm"] <= target_dmm <= b["dmm"]:
                frac = (target_dmm - a["dmm"]) / (b["dmm"] - a["dmm"])
                return (a[key] + frac * (b[key] - a[key])),\
                       (f"interpolated between {a['dmm']*100:g}% and {b['dmm']*100:g}% "
                        f"(scale factor {scale})")
        return hi[key], "using table maximum"

    def _target_dmm_fraction(self):
        """Validate the target DM/M % field -> fraction (0.02) or None (with an
        error dialog). Shared by the button and the starter-only completion."""
        try:
            target_pct = float(self.dt_target_dmm.get())
        except (TypeError, ValueError):
            self.log_msg("Suggest Min dt: Target DM/M % is not a number. Enter e.g. 2 for 2%.")
            return None
        if target_pct <= 0:
            self.log_msg("Suggest Min dt: Target DM/M % must be > 0 (e.g. 1-2% for an impact study).")
            return None
        return target_pct / 100.0

    def _offer_min_dt_from_out(self, path, jobname=None):
        """Parse a starter _0000.out's /DT/NODA/CST added-mass table and store the Min dt for the current target
        DM/M in self.min_dt_offer: {"seq", "job", "file", "dt", "note", "floor", "target_pct", "rows"} (the web client
        shows it and sets Min dt on confirmation), or {"error"}. Returns the offer."""
        target_dmm = self._target_dmm_fraction()
        if target_dmm is None:
            return None
        target_pct = target_dmm * 100.0
        base = os.path.basename(path)
        who = f" for {jobname}" if jobname else ""
        seq = (getattr(self, "min_dt_offer", None) or {}).get("seq", 0) + 1

        if not os.path.isfile(path):
            self.log_msg(f"Suggest Min dt: starter output not found{who}: {path}")
            self.min_dt_offer = {"seq": seq, "job": jobname, "file": path,
                                 "error": f"The starter output was not found{who}: {path}"}
            return self.min_dt_offer
        try:
            with open(path, "r", errors="ignore") as fh:
                text = fh.read()
        except OSError as e:
            self.min_dt_offer = {"seq": seq, "job": jobname, "file": path, "error": f"Could not read the file: {e}"}
            return self.min_dt_offer

        parsed = self._parse_added_mass_table(text)
        dt, note = self._recommend_min_dt(parsed, target_dmm, "0.9")

        if dt is None:
            self.log_msg(f"Suggest Min dt: {note} ({base}).")
            self.min_dt_offer = {"seq": seq, "job": jobname, "file": path, "error":
                                 f"No /DT/NODA/CST added-mass table was found in {base}. "
                                 "The starter prints it only when it completes its checks and the run uses "
                                 "/DT/NODA/CST timestep control. If the starter ERRORED, fix that first; "
                                 "otherwise confirm the deck uses /DT/NODA/CST."}
            return self.min_dt_offer

        floor = parsed.get("floor_dt")
        if floor:
            self.log_msg(f"Suggest Min dt from {base}: target {target_pct:g}% -> Min dt = {dt:.4g} s "
                         f"({note}). Floor dt = {floor:.4g} s.")
        else:
            self.log_msg(f"Suggest Min dt from {base}: target {target_pct:g}% -> Min dt = {dt:.4g} s "
                         f"({note}).")
        self.min_dt_offer = {"seq": seq, "job": jobname, "file": path, "dt": float(f"{dt:.4g}"), "note": note,
                             "floor": floor, "target_pct": target_pct,
                             "rows": [{"dmm": r["dmm"], "dt_09": r["dt_09"], "dt_067": r["dt_067"]}
                                      for r in sorted(parsed["rows"], key=lambda r: r["dmm"])]}
        return self.min_dt_offer

    def _gen_funct(self, func_id, name, data, scale=1.0, suffix=""):
        lines = [f"/FUNCT/{func_id}\n", f"{name}_Curve{suffix}\n", "#                  X                   Y\n"]
        for x, y in data['curve']: lines.append(f"{x:>20.5f}{y * scale:>20.5f}\n")
        return lines

    def _gen_fail_johnson(self, mat_id):
        """Johnson-Cook triaxiality-dependent failure card for a given material.
        Eps_f = [D1 + D2*exp(D3*sigma*)]*(1 + D4*ln(epsdot*))*(1 + D5*T*).
        Ixfem=0 => element deletion (not crack)."""
        def f(v):
            try: return float(v)
            except Exception: return 0.0
        def i(v):
            try: return int(float(v))
            except Exception: return 0
        d1, d2, d3, d4, d5 = f(self.jc_d1.get()), f(self.jc_d2.get()), f(self.jc_d3.get()), f(self.jc_d4.get()), f(self.jc_d5.get())
        eps0 = f(self.jc_eps0.get())
        ish = i(self.jc_ifail_sh.get()) or 1
        return [
            f"/FAIL/JOHNSON/{mat_id}\n",
            "#                 D1                  D2                  D3                  D4                  D5\n",
            f"{d1:>20.6g}{d2:>20.6g}{d3:>20.6g}{d4:>20.6g}{d5:>20.6g}\n",
            "#              EPS_0  Ifail_sh  Ifail_so                Dadv     Ixfem\n",
            f"{eps0:>20.6g}{ish:>10}{0:>10}{0.0:>20.6g}{0:>10}\n",
        ]

    def _resolve_tens_thresholds(self):
        """Resolve TENSSTRAIN et1/et2 exactly as the deck writer will, including
        the 'Plastic fail strain' fallback (v20.45). Returns (et1, et2, note).
        Shared by the card generator and the per-build settings report so the
        two can never disagree about what actually went into the deck."""
        def f(v):
            try: return float(v)
            except Exception: return 0.0
        et1, et2 = f(self.ts_et1.get()), f(self.ts_et2.get())
        note = ""
        if et1 <= 0.0 and et2 <= 0.0:
            try:
                fs_fb = float(self.fail_strain.get())
            except Exception:
                fs_fb = 0.0
            if fs_fb > 0.0:
                et1 = et2 = fs_fb
                note = (f"et1/et2 empty - using 'Plastic fail strain' = {fs_fb:g} for both "
                        "(immediate element deletion at that strain)")
            else:
                note = ("et1=et2=0 and 'Plastic fail strain' is also empty/0 - the starter "
                        "defaults these to 1e20: this card will NEVER fail an element")
        elif et2 <= 0.0:
            et2 = et1
            note = f"et2 empty - mirrored from et1 = {et1:g}"
        elif et1 <= 0.0 or et1 > et2:
            et1 = et2
            note = f"et1 empty/invalid - set equal to et2 = {et2:g}"

        # v20.67 softening band. When onset (et1) and rupture (et2) came out
        # EQUAL - the usual result of calibrating a single erosion strain - a
        # positive SoftBand spreads rupture above onset so stress ramps to zero
        # over a few cycles instead of one. This softens the impulse that feeds
        # the contact/mass-scaling instability. Distinct et1/et2 typed by the
        # user are respected as-is (band only fills the et1==et2 case).
        def _f(v):
            try: return float(v)
            except Exception: return 0.0
        band = _f(self.ts_soften.get())
        if et1 > 0.0 and et2 > 0.0:
            if band > 0.0 and abs(et2 - et1) <= 1e-12:
                et2 = et1 * (1.0 + band)
                extra = (f"SoftBand {band:g}: rupture et2 raised to {et2:g} "
                         f"({band*100:g}% above onset et1={et1:g}) so stress ramps to "
                         f"zero over several cycles instead of brittle one-cycle deletion")
                note = (note + "; " + extra) if note else extra
            elif band > 0.0 and et2 > et1:
                extra = (f"SoftBand {band:g} ignored - et1={et1:g} and et2={et2:g} are already "
                         f"distinct (using your typed band)")
                note = (note + "; " + extra) if note else extra
            elif band <= 0.0 and abs(et2 - et1) <= 1e-12:
                extra = (f"onset == rupture ({et1:g}): brittle one-cycle deletion. Set SoftBand "
                         f"> 0 (e.g. 0.08) to ramp stress to zero and ease the contact impulse")
                note = (note + "; " + extra) if note else extra
        return et1, et2, note

    def _gen_fail_tensstrain(self, mat_id):
        """/FAIL/TENSSTRAIN per the radioss2025 format (verified against the
        OpenRadioss starter reader and hm_cfg definition):
          card 1: Eps_t1, Eps_t2, fct_ID, Eps_f1, Eps_f2, S_Flag
          if S_Flag in {2,3,12,13,22,23}: element-size and temperature scaling
          cards are REQUIRED (written zeroed; the reader defaults zeros to 1.0);
          FAILIP card only when > 1 (reader default is 1; older input formats
          may misread a trailing card, so the default writes nothing).
        NOTE: S_Flag=1 (the solver default when the field is omitted) means
        EQUIVALENT strain - only 3/13/23 are actually max-principal criteria."""
        def f(v):
            try: return float(v)
            except Exception: return 0.0
        def i(v):
            try: return int(float(v))
            except Exception: return 0
        et1, et2, note = self._resolve_tens_thresholds()
        if note:
            tag = "FAILURE WARNING" if "NEVER" in note else "TENSSTRAIN"
            self.log_msg(f"  {tag} (mat {mat_id}): {note}.")
        sflag = i(self.ts_sflag.get()) or 23
        if sflag == 3:
            self.log_msg(f"  TENSSTRAIN (mat {mat_id}): S_Flag=3 - strain MEASURE follows the "
                         "property's Ismstr (implicit). 23 pins max principal TRUE strain explicitly.")
        failip = i(self.ts_failip.get()) or 1
        lines = [
            f"/FAIL/TENSSTRAIN/{mat_id}\n",
            "#         EPSILON_T1          EPSILON_T2    FCT_ID          EPSILON_F1          EPSILON_F2    S_Flag\n",
            f"{et1:>20.6g}{et2:>20.6g}{0:>10}{0.0:>20.6g}{0.0:>20.6g}{sflag:>10}\n",
        ]
        if sflag in (2, 3, 12, 13, 22, 23):
            lines += [
                "#  FCT_IDEL           FSCALE_EL              EI_REF\n",
                f"{0:>10}{0.0:>20.6g}{0.0:>20.6g}\n",
                "#  FCT_ID_T            FSCALE_T\n",
                f"{0:>10}{0.0:>20.6g}\n",
            ]
        if failip > 1:
            lines += ["#   FAILIP\n", f"{failip:>10}\n"]
        return lines

    def _flip_shell(self, nodes):
        """Reverse a shell's winding (flips its normal), keeping the first node."""
        if len(nodes) == 4: return [nodes[0], nodes[3], nodes[2], nodes[1]]
        if len(nodes) == 3: return [nodes[0], nodes[2], nodes[1]]
        return nodes

    def _orient_shells(self, conn):
        """Given {eid:[nodes]} for one shell part, return the set of eids whose winding
        must flip so all edge-adjacent elements traverse shared edges in opposite
        directions (consistent normals). Per connected patch, flips the minority."""
        from collections import defaultdict, deque
        edge_elems = defaultdict(list)
        for eid, nodes in conn.items():
            k = len(nodes)
            for a in range(k):
                fe = frozenset((nodes[a], nodes[(a + 1) % k]))
                if len(fe) == 2:
                    edge_elems[fe].append(eid)
        adj = defaultdict(set)
        for fe, elist in edge_elems.items():
            if len(elist) >= 2:
                for x in elist:
                    for y in elist:
                        if x != y: adj[x].add(y)
        flip, visited = set(), set()
        for seed in conn:
            if seed in visited: continue
            comp, comp_flip = [seed], set()
            visited.add(seed); dq = deque([seed])
            while dq:
                cur = dq.popleft()
                cur_nodes = self._flip_shell(conn[cur]) if cur in comp_flip else conn[cur]
                k = len(cur_nodes)
                cur_dir = {}
                for a in range(k):
                    p, q = cur_nodes[a], cur_nodes[(a + 1) % k]
                    cur_dir[frozenset((p, q))] = (p, q)
                for nb in adj[cur]:
                    if nb in visited: continue
                    visited.add(nb); comp.append(nb)
                    nb_nodes = conn[nb]; kk = len(nb_nodes)
                    for b in range(kk):
                        p, q = nb_nodes[b], nb_nodes[(b + 1) % kk]
                        fe = frozenset((p, q))
                        if fe in cur_dir:
                            if cur_dir[fe] == (p, q): comp_flip.add(nb)  # same dir => inconsistent
                            break
                    dq.append(nb)
            if len(comp_flip) > len(comp) / 2:      # flip the minority instead
                comp_flip = set(comp) - comp_flip
            flip |= comp_flip
        return flip

    def _heal_shell_normals(self, out_lines):
        """Make shell element normals consistent within each /SHELL part block."""
        new_lines = []
        i = 0
        total_flipped = parts = 0
        while i < len(out_lines):
            line = out_lines[i]
            if line.startswith('/SHELL/'):
                j = i + 1
                order, conn = [], {}
                while j < len(out_lines) and not out_lines[j].startswith('/'):
                    toks = out_lines[j].split()
                    if len(toks) >= 4 and toks[0].lstrip('-').isdigit():
                        eid = int(toks[0])
                        nodes = [int(t) for t in toks[1:5]] if len(toks) >= 5 else [int(t) for t in toks[1:4]]
                        nodes = [n for n in nodes if n != 0]
                        conn[eid] = nodes; order.append(eid)
                    j += 1
                try:
                    flips = self._orient_shells(conn)
                except Exception as e:
                    self.log_msg(f"Heal Normals: skipped a part ({e}).")
                    flips = set()
                for eid in flips:
                    conn[eid] = self._flip_shell(conn[eid])
                total_flipped += len(flips); parts += 1
                new_lines.append(line)
                for eid in order:
                    new_lines.append("".join(f"{v:>10}" for v in [eid] + conn[eid]) + "\n")
                i = j
                continue
            new_lines.append(line); i += 1
        if total_flipped:
            self.log_msg(f"Heal Normals: flipped {total_flipped} shell(s) across {parts} part(s) for consistent orientation.")
        else:
            self.log_msg(f"Heal Normals: {parts} shell part(s) checked; orientation already consistent.")
        return new_lines

# =========================================================================
    # SUBMITTER LOGIC
    # =========================================================================

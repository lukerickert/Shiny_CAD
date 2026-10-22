"""Deck build of the explicit analysis (ORC**3 workspace_build.py): the .inp -> OpenRadioss .rad translation
with inp2rad, card injection, ties, contact, rigidify, and _build_thread.

BuildMixin of the headless workspace (host.Workspace). The settings are self.<name> objects with get()/set()
(host.Var).
"""

import os
import sys
import json
import shutil
import subprocess
import glob
import tempfile
import re
from .constants import (CONTACT_T19, CONTACT_T24, CONTACT_T7, FAIL_JC, FAIL_TENS, MATERIAL_LIBRARY, NO_WINDOW, RBV_EXPL, RBV_PROFILE, RBV_PROFILE_F, SCRIPT_DIR, TIE_AUTO, TIE_GLOBAL, TIE_SCOPED)


class BuildMixin:
    def _parse_inp_ties(self, lines):
        """Parse PrePoMax/CalculiX *TIE definitions from the source INP into scoped
        ties. Returns dicts: name, tol, slave_nodes[], master_segs[[...]].
        Relies on node/element IDs, which inp2rad preserves."""
        import re as _re
        elem_conn, elsets, surfaces, ties = {}, {}, {}, []
        n = len(lines)
        def is_kw(s): return s.strip().startswith("*")
        i = 0
        while i < n:
            line = lines[i].strip(); low = line.lower()
            if low.startswith("*element"):
                i += 1; buf = []
                while i < n and not is_kw(lines[i]):
                    raw = lines[i].strip()
                    if raw:
                        toks = [t.strip() for t in raw.split(",") if t.strip() != ""]
                        buf.extend(toks)
                        if not raw.endswith(","):
                            try: elem_conn[int(buf[0])] = [int(x) for x in buf[1:]]
                            except Exception: pass
                            buf = []
                    i += 1
                continue
            if low.startswith("*elset"):
                mm = _re.search(r"elset\s*=\s*([^,\r\n]+)", line, _re.I)
                name = mm.group(1).strip() if mm else None
                i += 1; ids = []
                while i < n and not is_kw(lines[i]):
                    ids += [int(x) for x in _re.findall(r"\d+", lines[i])]; i += 1
                if name: elsets[name] = ids
                continue
            if low.startswith("*surface") and "element" in low:
                mm = _re.search(r"name\s*=\s*([^,\r\n]+)", line, _re.I)
                sname = mm.group(1).strip() if mm else None
                i += 1; entries = []
                while i < n and not is_kw(lines[i]):
                    parts = [p.strip() for p in lines[i].split(",") if p.strip()]
                    if parts: entries.append(parts[0])
                    i += 1
                if sname: surfaces[sname] = entries
                continue
            if low.startswith("*tie"):
                mm = _re.search(r"name\s*=\s*([^,\r\n]+)", line, _re.I)
                tname = mm.group(1).strip() if mm else "tie"
                tt = _re.search(r"position\s*tolerance\s*=\s*([0-9.eE+-]+)", line, _re.I)
                tol = float(tt.group(1)) if tt else 0.0
                i += 1
                while i < n and not lines[i].strip(): i += 1
                slave = master = None
                if i < n and not is_kw(lines[i]):
                    pr = [p.strip() for p in lines[i].split(",") if p.strip()]
                    if len(pr) >= 2: slave, master = pr[0], pr[1]
                    i += 1
                ties.append((tname, slave, master, tol))
                continue
            i += 1

        def surf_elems(sname):
            out = []
            for elset in surfaces.get(sname, []):
                out += elsets.get(elset, [])
            return out

        result = []
        for (tname, slave, master, tol) in ties:
            s_nodes = sorted({nd for e in surf_elems(slave) for nd in elem_conn.get(e, [])})
            m_segs = [elem_conn[e] for e in surf_elems(master) if e in elem_conn]
            result.append(dict(name=tname, tol=tol, slave_nodes=s_nodes, master_segs=m_segs))
        return result

    def _resolve_part(self, token, part_ids, part_name_map):
        """Resolve a part token (PID or case-insensitive name substring) to a PID."""
        t = (token or "").strip()
        if not t:
            return None, "empty"
        if t.isdigit():
            return (int(t), None) if int(t) in part_ids else (None, f"PID {t} not found")
        tu = t.upper()
        matches = [pid for pid, title in part_name_map.items() if tu in title.upper()]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"'{t}' matches parts {sorted(matches)}"
        return None, f"'{t}' matched no part"

    def _enable_shell_istrain(self, lines):
        """Set Istrain=1 on every /PROP/SHELL N-card so the strain TENSOR is written.
        For shell laws below LAW25 (e.g. LAW36/PLAS_TAB) Radioss only outputs the strain
        tensor when Istrain=1 in the property; inp2rad leaves it blank (0), which silently
        produces empty /ANIM/SHELL/TENS/STRAIN output. The N-card is:
            # N  Istrain  Thick  Ashear  Ithick  Iplas
        Idempotent: if Istrain is already present it is forced to 1."""
        out = list(lines)
        in_prop = False
        i = 0
        n_set = 0
        while i < len(out):
            s = out[i].strip()
            if s.startswith("/PROP/SHELL") or s.startswith("/PROP/TYPE1"):
                in_prop = True; i += 1; continue
            if in_prop and s.startswith("/"):
                in_prop = False
            if in_prop and out[i].lstrip().startswith("#"):
                u = out[i].upper()
                if ("THICK" in u) and ("ASHEAR" in u) and ("IPLAS" in u):
                    nl = "\r\n" if out[i].endswith("\r\n") else "\n"
                    out[i] = ("#        N    Istrain               Thick"
                              "              Ashear              Ithick     Iplas" + nl)
                    j = i + 1
                    while j < len(out) and (out[j].lstrip().startswith("#") or not out[j].strip()):
                        j += 1
                    if j < len(out):
                        toks = out[j].split()
                        dnl = "\r\n" if out[j].endswith("\r\n") else "\n"
                        if len(toks) == 5:
                            n, thick, ashear, ithick, iplas = toks
                        elif len(toks) >= 6:
                            n, _old, thick, ashear, ithick, iplas = toks[:6]
                        else:
                            in_prop = False; i = j + 1; continue
                        out[j] = (f"{n:>10}{'1':>10}{thick:>20}"
                                  f"{ashear:>20}{ithick:>10}{iplas:>10}" + dnl)
                        n_set += 1
                        in_prop = False
                        i = j + 1
                        continue
            i += 1
        if n_set:
            self.log_msg(f"Enabled strain-tensor output (Istrain=1) in {n_set} shell property block(s).")
        else:
            self.log_msg("WARNING: no /PROP/SHELL N-card found; strain tensor may be empty.")
        return out

    def _gen_rigidify(self, final_lines, part_ids, part_name_map):
        """v20.68: re-introduce the 'rigidify a part' injection removed in v20.59.
        For every entry in the Rigidify field (a PID or part-name substring),
        append three cards so the whole part moves as ONE rigid body while keeping
        its own structural mass:
          /NODE            a fresh free master node (high reserved ID, at origin)
          /GRNOD/PART/id   the group of ALL that part's nodes (the secondaries)
          /RBODY/id        ties them, with ICoG left at the solver default (1)
        ICoG=1 makes the STARTER compute the centre of gravity from the secondary
        nodes' element mass and MOVE the master node there - so we need no
        hand-computed coordinate and no /ADMAS density hack (mass is never faked
        by density here, per house rule). Ispher likewise defaults to 2. Only the
        master-node column (1) and the grnod column (5) carry values; every other
        field is 0 and any solver default fills in - so the card is unambiguous
        even without pinning the Mass column. No inertia card is written: the
        block ends at the next keyword and the starter derives inertia from the
        secondaries.
        The master node becomes the /RBODY main node, so the Impactor Velocity
        modes (/INIVEL or the load-hold-unload profile) drive it exactly like a
        PrePoMax reference point. Each rigidified part ADDS one /RBODY: if the
        model also defines its own, the single-/RBODY driver will report the
        ambiguity and write no velocity - rigidify OR keep the model RP, not both.
        Idempotent per part; unresolved / duplicate entries warn and are skipped."""
        raw = (self.rigid_part.get() or "")
        tokens = [t.strip() for t in raw.replace(",", "\n").splitlines() if t.strip()]
        if not tokens:
            return final_lines
        # reserved bands (clear of 999xxxx tie/velocity and 9999997-9 universal IDs)
        NID0, GID0, RID0 = 9970001, 9970101, 9970201
        add, done, seen = [], [], set()
        for k, tok in enumerate(tokens):
            pid, err = self._resolve_part(tok, part_ids, part_name_map)
            if pid is None:
                self.log_msg(f"RIGIDIFY WARNING: '{tok}' - {err}; nothing rigidified for this entry. "
                             f"Use 'List Parts' to see the PID/name of each /PART.")
                continue
            if pid in seen:
                self.log_msg(f"RIGIDIFY: part {pid} already rigidified; entry '{tok}' skipped.")
                continue
            seen.add(pid)
            nid, gid, rid = NID0 + k, GID0 + k, RID0 + k
            title = (part_name_map.get(pid, "") or f"PID_{pid}").strip()
            safe = (re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:40]) or f"PID_{pid}"
            # One physical line per list element (final_lines is scanned line-by-
            # line by the /RBODY and /INIVEL parsers, so bundled lines would hide
            # the title/main-node from them).
            add.append("/NODE\n")
            add.append(f"{nid:>10}{0.0:>20.6f}{0.0:>20.6f}{0.0:>20.6f}\n")
            add.append(f"/GRNOD/PART/{gid}\n")
            add.append(f"Rigidify_{safe}\n")
            add.append(f"{pid:>10}\n")
            add.append(f"/RBODY/{rid}\n")
            add.append(f"Rigidify_{safe}\n")
            add.append("#  node_ID   Sens_ID   Skew_ID    Ispher                Mass   grnd_ID     Ikrem      ICoG   surf_ID\n")
            # 9 fields: the Mass slot (0.0) sits between Ispher and grnd_ID. Omitting
            # it shifts grnd_ID into the Mass column -> grnd_ID reads 0 -> a lone main
            # node with no secondary group -> singular inertia tensor -> starter
            # Error 274. Mass=0.0 with ICoG=1 makes the starter build the inertia from
            # the rigidified part's own meshed nodes (real mass + spatial extent).
            _rb_line = f"{nid:>10}{0:>10}{0:>10}{0:>10}{0.0:>20.1f}{gid:>10}{0:>10}{1:>10}{0:>10}\n"
            _f = _rb_line.split()
            # Guard the exact defect that caused Error 274: a /RBODY main line must
            # carry 9 fields and a non-zero grnd_ID (field 6), or the starter builds a
            # single-node rigid body with singular inertia. Fail the build, not the run.
            if len(_f) != 9 or _f[5] == "0":
                raise ValueError(
                    f"RIGIDIFY: malformed /RBODY/{rid} main line for part {pid} - "
                    f"got {len(_f)} fields, grnd_ID={_f[5] if len(_f) > 5 else 'MISSING'}. "
                    f"Expected 9 fields with grnd_ID={gid} (cause: missing Mass column -> "
                    f"column shift -> singular inertia -> starter Error 274)."
                )
            add.append(_rb_line)
            done.append((pid, safe, nid, gid, rid))
        if not done:
            self.log_msg("RIGIDIFY: no part resolved from the Rigidify field - nothing injected.")
            return final_lines
        for pid, safe, nid, gid, rid in done:
            self.log_msg(f"Rigidified part {pid} ('{safe}'): /RBODY/{rid} over /GRNOD/PART/{gid} "
                         f"(all part nodes rigid), master /NODE {nid} relocated to the CoG by ICoG=1 "
                         f"(keeps the part's real mass). Drive it with an Impactor Velocity mode.")
        self.log_msg(f"RIGIDIFY: {len(done)} part(s) -> rigid bodies. Each adds ONE /RBODY; keep exactly "
                     f"one /RBODY in the deck if you also select an Explicit/profile velocity, or the "
                     f"driver will (correctly) refuse the ambiguous target.")
        return list(final_lines) + add

    def _resolve_inertia_payload(self, path):
        """Return (payload_dict, source_desc) from an inertia JSON at path.

        Accepts BOTH file shapes so the builder's two save formats are
        interchangeable here:
          1) flat payload (from 'Export /RBODY' or inertia_calc --rad):
             mass, cx, cy, cz, Jxx, Jyy, Jzz, Jxy, Jyz, Jxz  (used verbatim)
          2) primitives file (the builder's Save): units/primitives[/tilt] -
             computed on the spot via inertia_calc.compute (+ tilt rotation),
             which must sit next to the workspace scripts.
        Raises ValueError with the fix on anything else. Math stays in
        inertia_calc.py only; nothing is duplicated here.
        """
        if not os.path.isfile(path):
            raise ValueError(f"inertia JSON not found: {path}. "
                             f"Fix: pick a valid file, or clear the field.")
        try:
            with open(path, "r", errors="ignore") as fh:
                data = json.load(fh)
        except Exception as e:
            raise ValueError(f"could not read {path} ({e}).")
        pay = data.get("rbody") or data.get("payload") or data
        need = ("mass", "cx", "cy", "cz", "Jxx", "Jyy", "Jzz", "Jxy", "Jyz", "Jxz")
        if all(k in pay for k in need):
            return {k: float(pay[k]) for k in need}, "flat payload"
        if isinstance(data.get("primitives"), list) and data["primitives"]:
            try:
                from .inertia_calc import compute, rotation_matrix, rotate_tensor
            except ImportError:
                raise ValueError(
                    "this is a PRIMITIVES file (box definitions), and computing "
                    "from it needs inertia_calc.py next to the workspace scripts "
                    "- not found. Fix: copy inertia_calc.py there, or export the "
                    "flat payload from the builder instead.")
            M, cg, I, _ = compute(data["primitives"])
            t = data.get("tilt")
            if isinstance(t, dict) and float(t.get("deg", 0)) != 0.0:
                I = rotate_tensor(I, rotation_matrix(str(t["axis"]), float(t["deg"])))
            return ({"mass": M, "cx": cg[0], "cy": cg[1], "cz": cg[2],
                     "Jxx": I[0][0], "Jyy": I[1][1], "Jzz": I[2][2],
                     "Jxy": I[0][1], "Jyz": I[1][2], "Jxz": I[0][2]},
                    f"computed from {len(data['primitives'])} primitive(s)"
                    + (f", tilted {t['deg']}deg about {t['axis']}"
                       if isinstance(t, dict) and float(t.get('deg', 0)) != 0.0 else ""))
        miss = [k for k in need if k not in pay]
        raise ValueError(
            f"unrecognised inertia JSON (missing {miss}, and no 'primitives' "
            f"list). Fix: use the builder's 'Export /RBODY' output, or its "
            f"primitives Save file.")

    def _gen_point_mass(self, final_lines):
        """v20.71: concentrated-mass impactor, MERGED into the model's rigid body.

        Reads an inertia_calc.py payload (mass, cx..cz, Jxx..Jxz) and applies it
        by cases on how many /RBODY blocks the deck already carries (including
        any just added by _gen_rigidify, which runs first):

        EXACTLY ONE  -> the payload becomes THAT body's added mass + inertia:
          - Mass column := payload mass, ICoG := 3 (CG at the main node,
            added mass/inertia used verbatim), Ispher := 0; node_ID, Sens,
            Skew, grnd_ID, Ikrem, surf_ID are preserved from the original.
          - the inertia is written as TWO lines (Jxx Jyy Jzz / Jxy Jyz Jxz):
            six values on one line is 120 cols and Radioss reads 100, so the
            products would be silently truncated (v20.70 defect, fixed here).
          - the body's MAIN NODE is left where the model put it (ICoG=3 takes
            the CG to be that node). The payload cx/cy/cz are IGNORED on merge
            - they live in the builder's frame, and the model's reference point
            is authoritative. Moving the node dragged the rigid body off into
            the payload frame (v20.71.0 defect); fixed in v20.71.1.
          One body, with the model's contact surface AND the correct mass,
          CG and inertia - and a single unambiguous /INIVEL target.

        NONE -> falls back to the v20.70 free-node body (a lone /NODE at the
          CG carrying the payload). Valid for pure ballast studies, but it has
          NO CONTACT SURFACE - nothing can strike it - so this is logged as a
          loud caveat, not silently accepted.

        SEVERAL -> ambiguous, and no automatic choice is defensible: the build
          FAILS naming every /RBODY id so the user removes all but one (the
          same rule the single-/RBODY velocity driver enforces).
        """
        raw = (self.point_mass_json.get() or "").strip()
        if not raw:
            return final_lines
        try:
            pay, src_desc = self._resolve_inertia_payload(raw)
        except ValueError as e:
            raise ValueError(f"CONCENTRATED MASS: {e}")
        m = pay["mass"]
        cg = [pay["cx"], pay["cy"], pay["cz"]]
        J = [pay[k] for k in ("Jxx", "Jyy", "Jzz", "Jxy", "Jyz", "Jxz")]
        if m <= 0.0:
            raise ValueError(f"CONCENTRATED MASS: mass must be > 0, got {m}.")
        if J[0] <= 0 or J[1] <= 0 or J[2] <= 0:
            raise ValueError(f"CONCENTRATED MASS: diagonal inertia must be > 0 "
                             f"(Jxx,Jyy,Jzz = {J[0]},{J[1]},{J[2]}). A zero "
                             f"principal inertia is a singular tensor -> Error 274.")

        lines = list(final_lines)

        def _strip(s):
            return s.rstrip("\r\n")

        # ---- inventory of existing /RBODY blocks --------------------------
        rb_idx = [k for k, l in enumerate(lines) if _strip(l).startswith("/RBODY/")]

        def _inertia_lines():
            return [
                "#                Jxx                 Jyy                 Jzz\n",
                f"{J[0]:>20.6E}{J[1]:>20.6E}{J[2]:>20.6E}\n",
                "#                Jxy                 Jyz                 Jxz\n",
                f"{J[3]:>20.6E}{J[4]:>20.6E}{J[5]:>20.6E}\n",
                "#  Ioptoff\n",
                f"{0:>10}\n",
            ]

        off = max(abs(J[3]), abs(J[4]), abs(J[5]))
        diag = max(abs(J[0]), abs(J[1]), abs(J[2]))

        # ================= CASE: several bodies -> refuse ==================
        if len(rb_idx) > 1:
            ids = [_strip(lines[k]).split("/")[-1] for k in rb_idx]
            raise ValueError(
                "CONCENTRATED MASS: the deck already has %d /RBODY blocks (ids: %s). "
                "The payload merges into a SINGLE rigid body; with several the "
                "target is ambiguous (and the velocity driver would refuse too). "
                "Fix: keep exactly one rigid body (remove the extra rigid-body "
                "ties from the INP, or clear extra Rigidify entries), then rebuild."
                % (len(rb_idx), ", ".join(ids)))

        # ================= CASE: exactly one -> merge ======================
        if len(rb_idx) == 1:
            k0 = rb_idx[0]
            rid = _strip(lines[k0]).split("/")[-1]
            title = _strip(lines[k0 + 1]) if k0 + 1 < len(lines) else ""
            # main line = first non-blank, non-comment line after the title
            k = k0 + 2
            while k < len(lines) and (not _strip(lines[k]).strip()
                                      or _strip(lines[k]).lstrip().startswith("#")):
                k += 1
            if k >= len(lines):
                raise ValueError(f"CONCENTRATED MASS: /RBODY/{rid} has no main line - deck malformed.")
            f = _strip(lines[k]).split()
            if len(f) < 6:
                raise ValueError(
                    f"CONCENTRATED MASS: /RBODY/{rid} main line has {len(f)} fields "
                    f"(expected 9) - cannot merge into a malformed body.")
            nid = f[0]
            sens, skew = f[1], f[2]
            grnd = f[5]
            ikrem = f[6] if len(f) > 6 else "0"
            surf = f[8] if len(f) > 8 else "0"
            # end of the original block: next keyword line after k0
            kend = k0 + 1
            while kend < len(lines) and not _strip(lines[kend]).startswith("/"):
                kend += 1
            block = []
            block.append(f"/RBODY/{rid}\n")
            block.append((title or f"Merged_Concentrated_Mass_{rid}") + "\n")
            block.append("#  node_ID   Sens_ID   Skew_ID    Ispher                Mass   grnd_ID     Ikrem      ICoG   surf_ID\n")
            main_line = (f"{nid:>10}{sens:>10}{skew:>10}{0:>10}{m:>20.6E}"
                         f"{grnd:>10}{ikrem:>10}{3:>10}{surf:>10}\n")
            mf = main_line.split()
            # Guard: 9 fields, grnd_ID preserved verbatim, Mass non-zero. A
            # column shift here reproduces the Error-274 defect on the MODEL's
            # own rigid body - fail the build, never the run.
            if len(mf) != 9 or mf[5] != grnd or float(mf[4]) == 0.0:
                raise ValueError(
                    f"CONCENTRATED MASS: malformed merged /RBODY/{rid} main line "
                    f"({len(mf)} fields, grnd_ID={mf[5] if len(mf) > 5 else 'MISSING'}, "
                    f"expected grnd_ID={grnd}).")
            block.append(main_line)
            block.extend(_inertia_lines())
            lines = lines[:k0] + block + lines[kend:]

            # DO NOT move the main node. v20.71.1: the model's rigid body already
            # has its reference point placed deliberately (PrePoMax RP "at the
            # CoG"), and every secondary shell is tied to it. Relocating that node
            # to the payload CG dragged the whole rigid body off to a point in the
            # payload's OWN coordinate frame (which is generally NOT the model's
            # global frame) - the "impactor flew away" defect. With ICoG=3 the
            # solver takes the CG to BE the existing main node, so leaving the
            # node put means the inertia we write is about that reference point.
            # The payload's cx/cy/cz are therefore ignored on merge (they belong
            # to the builder's frame); only mass + the six inertia terms are used.
            # If the payload CG and the RP disagree, that is a frame mismatch for
            # the user to reconcile, NOT something to silently "fix" by moving the
            # model's geometry.
            self.log_msg(
                f"CONCENTRATED MASS (merged): /RBODY/{rid} now carries mass={m:.6g}, "
                f"ICoG=3, Ispher=0; grnd_ID={grnd} (contact mesh preserved). Inertia "
                f"Jxx/Jyy/Jzz={J[0]:.4g}/{J[1]:.4g}/{J[2]:.4g}, products Jxy/Jyz/Jxz="
                f"{J[3]:.4g}/{J[4]:.4g}/{J[5]:.4g} written as two 3-field lines. "
                f"Main node {nid} left AT the model's reference point (ICoG=3 takes "
                f"the CG to be that node); payload cx/cy/cz ignored on merge - the "
                f"inertia is applied about the existing RP. Source: {os.path.basename(raw)} ({src_desc}).")
            if diag > 0 and off / diag > 0.05:
                self.log_msg(
                    f"CONCENTRATED MASS: products of inertia are {100*off/diag:.1f}% of "
                    f"the diagonal - full tensor written, as it must be. NOTE: these "
                    f"products are about the payload's axes; if the model RP axes differ, "
                    f"re-express the tensor in the model frame (tilt in the builder).")
            self.log_msg(
                "CONCENTRATED MASS: ONE rigid body in the deck - the velocity driver "
                "has an unambiguous target and the body keeps its contact surface and "
                "reference-point location.")
            return lines

        # ================= CASE: none -> free-node fallback ================
        nid, rid = 9971001, 9971201
        add = []
        add.append("/NODE\n")
        add.append(f"{nid:>10}{cg[0]:>20.6f}{cg[1]:>20.6f}{cg[2]:>20.6f}\n")
        add.append(f"/RBODY/{rid}\n")
        add.append("Concentrated_Mass_Impactor\n")
        add.append("#  node_ID   Sens_ID   Skew_ID    Ispher                Mass   grnd_ID     Ikrem      ICoG   surf_ID\n")
        _rb_line = (f"{nid:>10}{0:>10}{0:>10}{0:>10}{m:>20.6E}"
                    f"{0:>10}{0:>10}{3:>10}{0:>10}\n")
        _f = _rb_line.split()
        if len(_f) != 9:
            raise ValueError(f"CONCENTRATED MASS: malformed /RBODY/{rid} main line "
                             f"({len(_f)} fields, expected 9).")
        if _f[5] != "0":
            raise ValueError(f"CONCENTRATED MASS: /RBODY/{rid} grnd_ID must be 0 for a "
                             f"free-node concentrated mass, got {_f[5]}.")
        if float(_f[4]) == 0.0:
            raise ValueError(f"CONCENTRATED MASS: /RBODY/{rid} Mass column is 0 with no "
                             f"secondary group -> singular inertia -> Error 679/274.")
        add.append(_rb_line)
        add.extend(_inertia_lines())
        self.log_msg(
            f"CONCENTRATED MASS (free node): no /RBODY in the deck, so /RBODY/{rid} was "
            f"created on free /NODE {nid} at the CG ({cg[0]:.4g}, {cg[1]:.4g}, {cg[2]:.4g}), "
            f"mass={m:.6g}, ICoG=3. Source: {os.path.basename(raw)} ({src_desc}).")
        self.log_msg(
            "CONCENTRATED MASS CAVEAT: a free-node rigid body has NO CONTACT SURFACE - "
            "nothing can strike it. For an impact, mesh the interface geometry and "
            "rigidify it (or use an INP rigid body): the payload then merges into that "
            "body automatically.")
        return lines + add

    def _select_target_rbody(self, rbodies, target):
        """Resolve which /RBODY the velocity/profile driver should drive.

        rbodies : list of (rbid, title, main_node_id) collected from the deck.
        target  : the 'Target RP' field - a /RBODY name or id; blank = auto.

        Blank target keeps the legacy rule: exactly one /RBODY must exist. A
        non-blank target selects that specific body even when several exist
        (the two-grip coupon case), matching by id first, then exact title,
        then title substring (case-insensitive on the title).

        Returns (rbody_tuple, None) on success, or (None, reason) on failure
        so the caller can log one clear warning.
        """
        target = (target or "").strip()
        if not target:
            if not rbodies:
                return None, "the deck contains NO /RBODY to drive"
            if len(rbodies) > 1:
                listing = "; ".join(f"/RBODY/{r} '{t}'" for r, t, mn in rbodies)
                return None, (f"the deck has {len(rbodies)} /RBODY and no 'Target RP' is set - "
                              f"ambiguous; type the /RBODY name or id in Target RP ({listing})")
            return (rbodies[0], None) if rbodies[0][2] is not None else \
                   (None, f"could not parse the main node of /RBODY/{rbodies[0][0]}")
        hit = [rb for rb in rbodies if str(rb[0]) == target]
        if not hit:
            tl = target.lower()
            hit = [rb for rb in rbodies if (rb[1] or "").strip().lower() == tl]
        if not hit:
            tl = target.lower()
            hit = [rb for rb in rbodies if tl in (rb[1] or "").lower()]
        if not hit:
            listing = "; ".join(f"/RBODY/{r} '{t}'" for r, t, mn in rbodies)
            return None, f"Target RP '{target}' matched no /RBODY (available: {listing})"
        if len(hit) > 1:
            listing = "; ".join(f"/RBODY/{r} '{t}'" for r, t, mn in hit)
            return None, f"Target RP '{target}' is ambiguous - matched {len(hit)} ({listing})"
        if hit[0][2] is None:
            return None, f"Target RP '{target}' (/RBODY/{hit[0][0]}) - could not parse its main node"
        return hit[0], None

    def _maybe_downgrade_quadratic(self, lines):
        """If 'Downgrade 2nd-order -> linear' is ticked, run the shared
        inp_to_linear.convert on the raw .inp so inp2rad (first-order only) can
        read it. Handles solids AND shells. No-op when unticked, when nothing
        quadratic is present, or (with a warning) if the helper module is
        missing. Never raises - returns the original lines on any failure."""
        if not getattr(self, "downgrade_quad", None) or not self.downgrade_quad.get():
            return lines
        try:
            from . import inp_to_linear as mod
        except Exception as e:
            self.log_msg(f"DOWNGRADE WARNING: inp_to_linear.py not importable ({e}); "
                         f"keep it in the workspace folder. Mesh left AS-IS (2nd-order).")
            return lines
        try:
            # prune=False: on an ASSEMBLED deck we must NOT drop nodes - a rigid
            # body's reference/main node, or nodes reached via *SURFACE or
            # *NSET,GENERATE, are attached to no element and would be pruned,
            # leaving the /RBODY pointing at an undefined node (starter ERROR 78
            # -> 442 -> 760 segfault). Orphaned midside nodes left behind are
            # inert (no element = no mass, no stiffness), so keeping them is safe.
            new_text, st = mod.convert("".join(lines), prune=False)
        except Exception as e:
            self.log_msg(f"DOWNGRADE WARNING: conversion failed ({e}); mesh left AS-IS.")
            return lines
        if st.get("converted"):
            summary = ", ".join(f"{t}->{mod.MAP[t][0]} x{c}" for t, c in st["converted"].items())
            self.log_msg(f"Downgrade 2nd-order -> linear: {summary}. Midside nodes KEPT "
                         f"(inert if unused; preserved so rigid bodies / sets / surfaces "
                         f"keep their node references).")
            if st.get("passed"):
                self.log_msg(f"DOWNGRADE WARNING: unrecognised element type(s) left unchanged: "
                             f"{', '.join(sorted(st['passed']))} - inp2rad may still halt on these.")
            return new_text.splitlines(keepends=True)
        self.log_msg("Downgrade 2nd-order -> linear: no quadratic elements found "
                     "(deck already linear); nothing changed.")
        return lines

    def _repair_missing_rbody_nodes(self, rad_lines, src_inp_lines=None):
        """Self-heal /RBODY main nodes that are missing from /NODE (starter
        ERROR 78 -> 442 -> 760 segfault). Preferred source of truth: the node's
        REAL coordinates harvested from the source .inp (PrePoMax does export
        RP nodes; they can be lost in intermediate processing). Fallback: the
        centroid of the body's secondary /GRNOD group (adequate for a
        translation-driven grip, but moment readouts about the RP would shift
        - hence the source-coordinate route is preferred). Returns the
        (possibly) repaired lines."""
        def _s(l): return l.strip()
        # ---- true coordinates from the source .inp (v20.74.1) ---------------
        src_xyz = {}
        if src_inp_lines:
            in_n = False
            for l in src_inp_lines:
                u = _s(l).upper()
                if u.startswith("*NODE") and "FILE" not in u and "PRINT" not in u \
                        and "OUTPUT" not in u:
                    in_n = True; continue
                if u.startswith("*"):
                    in_n = False; continue
                if in_n and _s(l) and not u.startswith("**"):
                    p = [t.strip() for t in l.split(",")]
                    if p and p[0].isdigit():
                        try:
                            src_xyz[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
                        except (IndexError, ValueError):
                            pass
        # ---- collect defined node ids and coordinates -----------------------
        node_xyz, in_node = {}, False
        for l in rad_lines:
            s = _s(l)
            if s.startswith("/NODE"):
                in_node = True; continue
            if in_node and s.startswith("/"):
                in_node = False
            if in_node and s and not s.startswith("#"):
                p = s.split()
                if p and p[0].lstrip("-").isdigit():
                    try:
                        node_xyz[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
                    except (IndexError, ValueError):
                        pass
        if not node_xyz:
            return rad_lines
        # ---- collect /GRNOD/NODE groups (id -> member node ids) -------------
        grnod, cur = {}, None
        for l in rad_lines:
            s = _s(l)
            if s.startswith("/GRNOD/NODE/"):
                try: cur = int(s.split("/")[3])
                except (IndexError, ValueError): cur = None
                if cur is not None: grnod[cur] = []
                continue
            if s.startswith("/"):
                cur = None; continue
            if cur is not None and s and not s.startswith("#"):
                for t in s.split():
                    if t.lstrip("-").isdigit():
                        grnod[cur].append(int(t))
        # ---- scan /RBODY blocks: main node defined? -------------------------
        missing = []   # (rbid, main_id, gnod_id)
        i = 0
        while i < len(rad_lines):
            s = _s(rad_lines[i])
            if s.startswith("/RBODY/"):
                try: rbid = int(s.split("/")[2])
                except (IndexError, ValueError): rbid = "?"
                j = i + 1
                while j < len(rad_lines) and (not _s(rad_lines[j]) or
                                              _s(rad_lines[j]).startswith("#") or
                                              not _s(rad_lines[j]).split()[0].lstrip("-").isdigit()):
                    j += 1
                if j < len(rad_lines):
                    f = _s(rad_lines[j]).split()
                    if len(f) >= 6:
                        try:
                            main_id, gnod_id = int(f[0]), int(f[5])
                            if main_id not in node_xyz:
                                missing.append((rbid, main_id, gnod_id))
                        except ValueError:
                            pass
                i = j
            i += 1
        if not missing:
            return rad_lines
        # ---- synthesize the missing nodes at their grip centroids -----------
        add = ["#---1----|----2----|----3----|----4----|----5----|----6----|----7----|----8----|----9----|---10----|\n",
               "# v20.74.1 REPAIR: /RBODY main node(s) were missing from /NODE. Restored\n",
               "# from the source .inp coordinates where available, else placed at the\n",
               "# centroid of the rigid body's secondary group.\n",
               "/NODE\n"]
        for rbid, main_id, gnod_id in missing:
            if main_id in src_xyz:
                cx, cy, cz = src_xyz[main_id]
                src = "TRUE coordinates from the source .inp"
            else:
                members = [n for n in grnod.get(gnod_id, []) if n in node_xyz]
                if members:
                    cx = sum(node_xyz[n][0] for n in members) / len(members)
                    cy = sum(node_xyz[n][1] for n in members) / len(members)
                    cz = sum(node_xyz[n][2] for n in members) / len(members)
                    src = f"centroid of /GRNOD/NODE/{gnod_id} ({len(members)} nodes) - source .inp had no coordinates"
                else:
                    cx = cy = cz = 0.0
                    src = f"ORIGIN - /GRNOD/NODE/{gnod_id} empty/unresolved and no source coordinates, VERIFY"
            add.append(f"{main_id:10d}{cx:20.10g}{cy:20.10g}{cz:20.10g}\n")
            self.log_msg(f"REPAIR: /RBODY/{rbid} main node {main_id} was undefined - created at {src}: "
                         f"({cx:.4g}, {cy:.4g}, {cz:.4g}).")
        # insert before /END if present, else append
        out = list(rad_lines)
        for k in range(len(out) - 1, -1, -1):
            if _s(out[k]).startswith("/END"):
                return out[:k] + add + out[k:]
        return out + add

    def _build_thread(self):
        self.log_msg("\n--- STARTING BUILD PROCESS ---")
        inp_file = self.inp_path.get()
        out_dir = self.out_dir.get()
        self.log_msg(f"Reading input from {inp_file} ...")
        
        if not os.path.exists(inp_file):
            self.log_msg("Error: INP file does not exist.")
            return

        # v20.65 pre-flight: the source must be a MESHED Abaqus .inp (with
        # *NODE/*ELEMENT), not CAD geometry. Feeding a STEP/IGES/BREP file
        # produces a deck with no /NODE and the starter dies with the cryptic
        # "THERE IS NO DEFINED NODE" - catch it here with the cause and fix.
        _ext = os.path.splitext(inp_file)[1].lower()
        if _ext in (".stp", ".step", ".igs", ".iges", ".brep", ".x_t", ".x_b", ".sat"):
            self.log_msg(f"BUILD HALTED: '{os.path.basename(inp_file)}' is a CAD GEOMETRY file "
                         f"({_ext}), which has no mesh. inp2rad converts a MESHED Abaqus .inp, so "
                         f"this yields a deck with no /NODE and the starter stops with 'THERE IS NO "
                         f"DEFINED NODE'. FIX: in PrePoMax, import the mesh (e.g. the target_block.inp "
                         f"/ indenter.inp orphan meshes), assign sections/rigid body/BCs and a Dynamic "
                         f"Explicit step, then File > Export as CalculiX .inp and point Source at that.")
            return
        try:
            with open(inp_file, "r", errors="ignore") as _fh:
                _head = _fh.read(200000).upper()
            if "*NODE" not in _head:
                self.log_msg(f"BUILD HALTED: '{os.path.basename(inp_file)}' contains no *NODE block - "
                             f"it is not a meshed Abaqus .inp (a starter needs /NODE). FIX: export the "
                             f"MESHED model from PrePoMax (File > Export, CalculiX .inp) and use that "
                             f"file; a geometry-only or empty export will not run.")
                return
        except Exception as e:
            self.log_msg(f"BUILD HALTED: could not read the source file to check for a mesh ({e}).")
            return
            
        target_dir = out_dir if out_dir and os.path.isdir(out_dir) else os.path.dirname(inp_file)
        model_name = os.path.splitext(os.path.basename(inp_file))[0]

        # Sequential build number: repeat builds into the same folder get unique
        # deck/job names (MODEL_b01, MODEL_b02, ...) instead of overwriting the
        # previous decks and results. The suffix flows through everywhere the
        # job name is used: engine /RUN/ card, A-files, T-files, .vtk, CSVs.
        # v20.46: the scan also covers per-build subfolders (decks inside them
        # AND bare folder names, so a purged/empty folder still bumps the number).
        bno = 0
        try:
            cands = (glob.glob(os.path.join(target_dir, f"{model_name}_b*_0000.rad")) +
                     glob.glob(os.path.join(target_dir, f"{model_name}_b*", f"{model_name}_b*_0000.rad")))
            for p in cands:
                m = re.search(r"_b(\d+)_0000\.rad$", os.path.basename(p))
                if m:
                    bno = max(bno, int(m.group(1)))
            dre = re.compile(rf"^{re.escape(model_name)}_b(\d+)$")
            for nm in os.listdir(target_dir):
                m = dre.match(nm)
                if m and os.path.isdir(os.path.join(target_dir, nm)):
                    bno = max(bno, int(m.group(1)))
        except Exception:
            pass
        base_name = model_name
        model_name = f"{base_name}_b{bno + 1:02d}"
        self.log_msg(f"Build number b{bno + 1:02d} — job name: {model_name}")

        # One glanceable record of what this build will do; also lands in the
        # run's console.log so every deck's provenance is readable later.
        self.log_msg("--- BUILD SETTINGS ---")
        self.log_msg(f"  Source: {inp_file}")
        self.log_msg(f"  Output: {target_dir}")
        self.log_msg(f"  Test mode: {self.test_mode.get()} | tstop={self.tstop.get()} | "
                     f"frames={self.anim_frames.get()} | fric={self.fric.get()}")
        mats = [f"'{m.get()}' -> model name '{n.get()}'"
                for m, n in self._mat_slots()
                if not m.get().startswith("None")]
        self.log_msg(f"  Library materials: {'; '.join(mats) if mats else '(none - PrePoMax data kept)'}")
        fm = self.fail_model.get()
        fdetail = ""
        if fm == FAIL_JC:
            fdetail = (f" | D1..D5=({self.jc_d1.get()},{self.jc_d2.get()},{self.jc_d3.get()},"
                       f"{self.jc_d4.get()},{self.jc_d5.get()}) e0={self.jc_eps0.get()} Ifail_sh={self.jc_ifail_sh.get()}")
        elif fm == FAIL_TENS:
            _r1, _r2, _rn = self._resolve_tens_thresholds()
            fdetail = (f" | et1={self.ts_et1.get()} et2={self.ts_et2.get()} "
                       f"SoftBand={self.ts_soften.get()} -> written EPSILON_T1={_r1:g} "
                       f"EPSILON_T2={_r2:g} | S_Flag={self.ts_sflag.get()} FAILIP={self.ts_failip.get()}")
            if _rn:
                fdetail += f" [{_rn}]"
        self.log_msg(f"  Failure model: {fm} | plastic fail strain: {self.fail_strain.get() or '(empty)'}{fdetail}")
        rb_extra = (f" ({self.rigid_vel.get() or 'EMPTY Vx Vy Vz!'})"
                    if self.rigid_vel_mode.get() == RBV_EXPL else "")
        self.log_msg(f"  Tie mode: {self.tie_mode.get()} | Impactor velocity: {self.rigid_vel_mode.get()}{rb_extra}")

        # Build on fast local disk, then copy the finished decks to target_dir.
        # target_dir is often the Tailscale-mounted Z: share; running inp2rad directly
        # there does thousands of slow SMB round-trips and makes the build appear to hang.
        try:
            build_dir = tempfile.mkdtemp(prefix="orbuild_")
        except Exception as e:
            self.log_msg(f"Error: could not create local build folder: {e}"); return
        work_dir = build_dir
        if os.path.normpath(target_dir) != os.path.normpath(build_dir):
            self.log_msg(f"Building locally, copying final decks to: {target_dir}")
        
        bcs = []
        try:
            with open(inp_file, 'r') as f: lines = f.readlines()
            lines = self._maybe_downgrade_quadratic(lines)
            in_vel = False
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("**"): continue
                if stripped.upper().startswith("*BOUNDARY"):
                    in_vel = True if "TYPE=VELOCITY" in stripped.upper() else False
                    continue
                elif stripped.startswith("*"): in_vel = False
                
                if in_vel:
                    parts = [p.strip() for p in stripped.split(",")]
                    if len(parts) >= 4:
                        bcs.append({"nset": parts[0].upper(), "dof": int(parts[1]), "mag": float(parts[3])})
        except: pass
        
        safe_inp_file = os.path.join(work_dir, f"safe_{model_name}.inp")
        try:
            with open(safe_inp_file, 'w') as f:
                in_vel = False
                for line in lines:
                    stripped = line.strip()
                    if stripped.upper().startswith("*BOUNDARY") and "TYPE=VELOCITY" in stripped.upper():
                        in_vel = True; continue
                    elif in_vel and stripped.startswith("*"): in_vel = False
                    if not in_vel: f.write(line)
        except Exception as e:
            self.log_msg(f"Error creating Safe INP: {e}"); return

        inp2rad_path = os.path.join(SCRIPT_DIR, "inp2rad.py")
        if not os.path.exists(inp2rad_path):
            self.log_msg("Error: inp2rad.py not found in script directory."); return
            
        self.log_msg("Running inp2rad converter...")
        try:
            # inp2rad pauses with input() for each construct it cannot handle; feed
            # plenty of answers so prompt-heavy conversions don't crash on stdin EOF.
            conv = subprocess.run([sys.executable, os.path.join(SCRIPT_DIR, "inp2rad_run.py"), inp2rad_path, safe_inp_file],
                                  cwd=work_dir, input=("y\n" * 5000), text=True, capture_output=True,
                                  creationflags=NO_WINDOW)
        except Exception as e:
            self.log_msg(f"Converter failed to launch: {e}"); return

        # Surface what inp2rad actually reported, so failures are diagnosable.
        if conv.stdout and conv.stdout.strip():
            self.log_msg("--- inp2rad output ---")
            for ln in conv.stdout.strip().splitlines():
                self.log_msg(f"  {ln}")
        if conv.stderr and conv.stderr.strip():
            self.log_msg("--- inp2rad errors ---")
            for ln in conv.stderr.strip().splitlines():
                self.log_msg(f"  {ln}")
        self.log_msg(f"inp2rad exit code: {conv.returncode}")

        # Stop clearly if the mesh uses element types inp2rad can't convert, rather
        # than letting it emit an incomplete deck or crash on a prompt.
        unsupported = sorted(set(re.findall(r"Unknown element type\s+(\S+)", conv.stdout or "")))
        if unsupported:
            self.log_msg("")
            self.log_msg(f"BUILD HALTED: inp2rad cannot convert element type(s): {', '.join(unsupported)}.")
            self.log_msg("OpenCourant meshes are first-order, so higher-order elements aren't supported.")
            self.log_msg("Re-mesh the affected part(s) with linear elements in PrePoMax")
            self.log_msg("(e.g. S8/S8R shells -> S4R or S3; C3D20 solids -> C3D8), re-export, and rebuild.")
            return

        rad_file_safe = os.path.join(work_dir, f"safe_{model_name}_0000.rad")
        if not os.path.exists(rad_file_safe):
            # The converter may have written the deck under a slightly different name.
            candidates = sorted(glob.glob(os.path.join(work_dir, "safe_*_0000.rad")))
            if candidates:
                rad_file_safe = candidates[0]
                self.log_msg(f"Note: using converter output found at '{os.path.basename(rad_file_safe)}'.")
            else:
                self.log_msg("Error: inp2rad did not produce a .rad file. See the inp2rad output above for the cause.")
                self.log_msg(f"The stripped input is kept at '{os.path.basename(safe_inp_file)}' so you can run the converter on it manually.")
                rads = [os.path.basename(p) for p in glob.glob(os.path.join(work_dir, "*.rad"))]
                self.log_msg(f".rad files currently in the work folder: {', '.join(rads) if rads else '(none)'}")
                return

        with open(rad_file_safe, 'r') as f: rad_lines = f.readlines()
        rad_lines = self._repair_missing_rbody_nodes(rad_lines, src_inp_lines=lines)
        out_lines = []
        part_ids = []
        skip = False
        for line in rad_lines:
            clean_line = line.strip().upper()
            if line.startswith(f"safe_{model_name}"): 
                line = line.replace(f"safe_{model_name}", model_name)
            if clean_line.startswith('/PART/'):
                try: part_ids.append(int(clean_line.split('/')[2]))
                except: pass
            
            if clean_line.startswith('/SURF/') or clean_line.startswith('/INTER/') or clean_line.startswith('/GRNOD/SURF/') or clean_line.startswith('/TH/'): 
                skip = True
            elif skip and clean_line.startswith('/') and not clean_line.startswith('//'): 
                skip = False
                
            if not skip and not clean_line.startswith('/END'): 
                out_lines.append(line)

        grnod_map = {}
        for idx, line in enumerate(out_lines):
            if line.startswith("/GRNOD/NODE/"):
                grnod_id = line.strip().split('/')[-1]
                if idx + 1 < len(out_lines): grnod_map[out_lines[idx+1].strip().upper()] = grnod_id

        part_name_map = {}
        for idx, line in enumerate(out_lines):
            if line.startswith("/PART/"):
                try:
                    pid = int(line.strip().split('/')[2])
                    part_name_map[pid] = out_lines[idx + 1].strip() if idx + 1 < len(out_lines) else ""
                except Exception:
                    pass

        self.log_msg("Injecting Material Profiles...")
        temp_lines = []
        injected_funcs = []
        i = 0
        mat_names_found = []
        orphan_func_ids = set()
        jc_mat_ids = set()
        use_jc = self.fail_model.get().startswith("Johnson")
        use_tens = self.fail_model.get().startswith("Max principal")
        while i < len(out_lines):
            line = out_lines[i]
            if line.startswith("/MAT/"):
                try:
                    mat_id = int(line.split('/')[3].strip())
                    name = out_lines[i+1].strip()
                    name_u = name.upper()
                    mat_names_found.append(f"  ID {mat_id}: '{name}'")
                    mapping = None
                    for _mv, _nv in self._mat_slots():     # first slot with the model name wins (ORC**3: MAT1, MAT2, MAT3)
                        _t = _nv.get().strip().upper()
                        if _t and name_u == _t and _mv.get() in MATERIAL_LIBRARY:
                            mapping = MATERIAL_LIBRARY[_mv.get()]
                            break
                    if mapping:
                        # Capture only the function IDs this original material referenced
                        # (the line after the 'func_ID' comment header), so the now-orphaned
                        # original /FUNCT curves can be stripped. Reading every number in the
                        # block would wrongly grab N_funct / flag values.
                        for k in range(i + 2, len(out_lines)):
                            if out_lines[k].startswith('/'): break
                            if out_lines[k].strip().startswith('#') and 'func_id' in out_lines[k].lower():
                                m = k + 1
                                while m < len(out_lines) and out_lines[m].strip().startswith('#'): m += 1
                                if m < len(out_lines) and not out_lines[m].startswith('/'):
                                    for tok in out_lines[m].split():
                                        if tok.isdigit() and int(tok) > 0:
                                            orphan_func_ids.add(int(tok))
                                break
                        # v20.63: 10 reserved function IDs per material (>=9000
                        # keeps them clear of the orphan-curve stripper); the
                        # rate-dependent LAW36 path uses up to 5 of them.
                        func_id = 9000 + mat_id * 10
                        law = str(mapping.get("law", "LAW36")).upper()
                        if law == "LAW2":
                            temp_lines.extend(self._gen_law2(mat_id, name, mapping))
                            law_note = (f"LAW2/PLAS_JOHNS a={mapping.get('a')} b={mapping.get('b')} "
                                        f"n={mapping.get('n')} c={mapping.get('c')} eps0={mapping.get('eps0')}")
                        elif law == "LAW1":
                            temp_lines.extend(self._gen_law1(mat_id, name, mapping))
                            law_note = "LAW1/ELAST (elastic - no yield, no failure card)"
                        else:
                            table = self._lib_rate_table(mapping)
                            temp_lines.extend(self._gen_law36(mat_id, name, mapping, func_id))
                            for k, (rate, scale) in enumerate(table):
                                injected_funcs.extend(self._gen_funct(
                                    func_id + k, name, mapping, scale=scale,
                                    suffix=(f"_r{rate:g}" if len(table) > 1 else "")))
                            if len(table) > 1:
                                law_note = ("LAW36/PLAS_TAB rate-dependent, curves at eps_dot = " +
                                            ", ".join(f"{r:g}/s (DIF {s:.3f})" for r, s in table) +
                                            f" [Cowper-Symonds D={mapping.get('cs_D'):g}, q={mapping.get('cs_q'):g}]")
                            else:
                                law_note = "LAW36/PLAS_TAB (single static curve)"
                        if law == "LAW1":
                            if use_jc or use_tens:
                                self.log_msg(f"  NOTE: '{name}' is elastic LAW1 - no /FAIL card attached "
                                             "(elastic parts must not be deleted).")
                        elif use_jc:
                            temp_lines.extend(self._gen_fail_johnson(mat_id))
                            jc_mat_ids.add(mat_id)
                        elif use_tens:
                            temp_lines.extend(self._gen_fail_tensstrain(mat_id))
                            jc_mat_ids.add(mat_id)
                        self.log_msg(f"  REPLACED: '{name}' (ID {mat_id}) -> {law_note}." +
                                     (f"  + /FAIL/JOHNSON (triaxiality)." if (use_jc and law != "LAW1") else
                                      (f"  + /FAIL/TENSSTRAIN (max principal strain)." if (use_tens and law != "LAW1") else "")))
                        i += 2
                        while i < len(out_lines) and not out_lines[i].startswith('/'): i += 1
                        continue
                    else:
                        self.log_msg(f"  KEPT (no match): '{name}' (ID {mat_id}) - check 'Name in model' fields.")
                except: pass
            temp_lines.append(line)
            i += 1
        out_lines = temp_lines + injected_funcs
        if mat_names_found:
            self.log_msg(f"Materials found in deck: {', '.join(f.strip() for f in mat_names_found)}")

        # Strip the orphaned original plastic-curve functions left behind by replacement.
        # Never strip the freshly injected library curves (IDs 9001+) or other reserved IDs.
        if orphan_func_ids:
            cleaned = []
            j = 0
            stripped = []
            while j < len(out_lines):
                ln = out_lines[j]
                if ln.startswith('/FUNCT/'):
                    try:
                        fid = int(ln.strip().split('/')[-1])
                    except Exception:
                        fid = None
                    if fid in orphan_func_ids and fid < 9000:
                        stripped.append(fid)
                        j += 1
                        while j < len(out_lines) and not out_lines[j].startswith('/'): j += 1
                        continue
                cleaned.append(ln); j += 1
            out_lines = cleaned
            if stripped:
                self.log_msg(f"Removed orphaned original material curve(s): /FUNCT {sorted(stripped)}")

        if self.align_norms.get():
            out_lines = self._heal_shell_normals(out_lines)

        final_lines = []
        idx = 0
        fs = float(self.fail_strain.get()) if self.fail_strain.get().strip() else None
        if fs is None or fs <= 0.0:
            if use_jc or use_tens:
                self.log_msg("Failure note: 'Plastic fail strain' is empty/0 - materials KEPT from the model "
                             "(not library-replaced) will have NO strain failure; only library materials get "
                             "the /FAIL card.")
            else:
                self.log_msg("FAILURE WARNING: 'Plastic fail strain' is empty/0 with Equivalent-plastic-strain "
                             "mode - NO element failure will occur anywhere in this model.")
        v_rewrite = set()
        tstop = float(self.tstop.get())

        while idx < len(out_lines):
            line = out_lines[idx]
            if self.apply_vel_model.get() and line.startswith("/IMPDISP/"):
                try:
                    imp_id = line.strip().split('/')[-1]
                    name = out_lines[idx+1].strip()
                    j = idx + 2
                    while j < len(out_lines) and out_lines[j].startswith('#'): j += 1
                    p1 = out_lines[j].split()
                    ifct, dir_val, igrnd = p1[0], p1[1], p1[4]
                    j += 1
                    while j < len(out_lines) and out_lines[j].startswith('#'): j += 1
                    p2 = out_lines[j].split()
                    ascale = float(p2[0])
                    fscale = float(p2[1]) if len(p2) > 1 else 1.0
                    v_const = (ascale * fscale) / (tstop * 0.975)
                    final_lines.extend([
                        f"/IMPVEL/{imp_id}\n", f"{name}_Velocity\n",
                        f"{ifct:>10}{dir_val:>10}{0:>10}{0:>10}{igrnd:>10}\n",
                        f"{1.0:>20.5f}{v_const:>20.5f}{0.0:>20.5f}{tstop:>20.5f}\n"
                    ])
                    v_rewrite.add(ifct.strip()); idx = j + 1; continue
                except: pass 

            if line.startswith("/MAT/LAW2/") or line.startswith("/MAT/PLAS_JOHNS/"):
                # v20.63 FIX: Eps_p_max lives on the a/b/n row (4th data line
                # counting the title, cnt==3) at cols 61-80. The old patch hit
                # cols 81-100 of the E/Nu row - a field nothing reads - so kept
                # LAW2 materials silently had no failure. Like the LAW36 branch,
                # materials governed by an external /FAIL card are skipped.
                final_lines.append(line)
                try:
                    this_mat_id = int(line.strip().split('/')[-1])
                except Exception:
                    this_mat_id = None
                use_builtin_fs2 = this_mat_id not in jc_mat_ids
                cnt, sub_idx = 0, idx + 1
                while sub_idx < len(out_lines) and not out_lines[sub_idx].startswith('/'):
                    l = out_lines[sub_idx]
                    if not l.strip().startswith('#') and l.strip() and fs is not None and fs > 0.0 and use_builtin_fs2:
                        if cnt == 3: l = l.replace('\n', '').ljust(100)[:60] + f"{fs:>20.4f}" + l.replace('\n', '').ljust(100)[80:100] + "\n"
                        cnt += 1
                    elif not l.strip().startswith('#') and l.strip():
                        cnt += 1
                    final_lines.append(l); sub_idx += 1
                idx = sub_idx; continue

            elif line.startswith("/MAT/LAW36/") or line.startswith("/MAT/PLAS_TAB/"):
                final_lines.append(line)
                try:
                    this_mat_id = int(line.strip().split('/')[-1])
                except Exception:
                    this_mat_id = None
                use_builtin_fs = this_mat_id not in jc_mat_ids   # external /FAIL card governs => leave Eps_t/Eps_m = 0
                cnt, sub_idx = 0, idx + 1
                while sub_idx < len(out_lines) and not out_lines[sub_idx].startswith('/'):
                    l = out_lines[sub_idx]
                    if not l.strip().startswith('#') and l.strip():
                        if cnt == 2 and fs is not None and fs > 0.0 and use_builtin_fs: 
                            l = l.replace('\n', '').ljust(100)[:40] + f"{fs:>20.4f}{fs*0.99:>20.4f}{fs:>20.4f}\n"
                        elif cnt == 7: 
                            l = f"{0.0:>20.4f}" + l.replace('\n', '').ljust(100)[20:] + "\n" 
                        cnt += 1
                    final_lines.append(l); sub_idx += 1
                idx = sub_idx; continue

            elif line.startswith('/FUNCT/'):
                f_id = line.strip().split('/')[-1].strip()
                if self.apply_vel_model.get() and f_id in v_rewrite:
                    final_lines.extend([
                        line, out_lines[idx+1], 
                        f"{0.0:>20.5f}{0.0:>20.5f}\n", f"{tstop*0.05:>20.5f}{1.0:>20.5f}\n", f"{tstop:>20.5f}{1.0:>20.5f}\n"
                    ])
                    idx += 2
                    while idx < len(out_lines) and not out_lines[idx].startswith('/'): idx += 1
                    continue
                final_lines.append(line)
                sub_idx = idx + 1
                healed = False
                while sub_idx < len(out_lines) and not out_lines[sub_idx].startswith('/'):
                    l = out_lines[sub_idx]
                    if not l.strip().startswith('#') and l.strip() and not healed:
                        try:
                            if float(l[:20].strip()) > 0.0: final_lines.append(f"{0.0:>20.1f}{float(l[20:40].strip()):>20.4f}\n")
                            healed = True
                        except: pass
                    final_lines.append(l); sub_idx += 1
                idx = sub_idx; continue
            else:
                final_lines.append(line); idx += 1

        if self.apply_vel_model.get() and bcs:
            self.log_msg("Injecting Native INP Velocity Curves...")
            impvel_base_id = 8000
            for vbc in bcs:
                nset = vbc["nset"]
                grnd_id = grnod_map.get(nset, "0")
                if grnd_id == "0":
                    for k, v in grnod_map.items():
                        if nset in k: grnd_id = v; break
                d_str = {1: 'X', 2: 'Y', 3: 'Z'}.get(vbc["dof"], 'X')
                final_lines.extend([
                    f"/IMPVEL/{impvel_base_id}\n", f"Native_Velocity_{nset}_{d_str}\n",
                    f"{impvel_base_id:>10}{d_str:>10}{0:>10}{0:>10}{grnd_id:>10}\n",
                    f"{1.0:>20.5f}{vbc['mag']:>20.5f}{0.0:>20.5f}{tstop:>20.5f}\n",
                    f"/FUNCT/{impvel_base_id}\n", f"Native_Velocity_Ramp_{impvel_base_id}\n",
                    f"{0.0:>20.5f}{0.0:>20.5f}\n", f"{tstop*0.05:>20.5f}{1.0:>20.5f}\n", f"{tstop:>20.5f}{1.0:>20.5f}\n"
                ])
                impvel_base_id += 1

        final_lines = self._enable_shell_istrain(final_lines)

        # v20.68: rigidify requested parts BEFORE the /RBODY scan below, so the
        # injected bodies are both written into the deck and seen by the
        # Impactor Velocity driver (which finds /RBODY main nodes in final_lines).
        final_lines = self._gen_rigidify(final_lines, part_ids, part_name_map)

        # v20.69: concentrated-mass impactor (unmeshed lumped rigid body). Also
        # injected BEFORE the /RBODY scan below so its free master node is driven
        # by the Impactor Velocity modes exactly like a rigidified part's node.
        final_lines = self._gen_point_mass(final_lines)

        # Pre-flight: elements filed under nonexistent part 0 mean an element
        # set got NO section in PrePoMax; inp2rad converts them silently and
        # the starter dies later with ERROR ID 402. Halt now, with the fix.
        orphan_hdrs = sorted({l.strip().upper() for l in final_lines
                              if l.strip().upper() in ("/SHELL/0", "/SH3N/0")})
        if orphan_hdrs:
            self.log_msg("")
            self.log_msg(f"BUILD HALTED: the converted deck contains {', '.join(orphan_hdrs)} - "
                         "elements assigned to nonexistent part 0.")
            self.log_msg("Cause: one or more element sets have NO section assigned in PrePoMax "
                         "(every *ELEMENT/ELSET needs a *SHELL SECTION).")
            self.log_msg("Fix: assign the missing section(s) in PrePoMax, re-export the .inp and "
                         "rebuild. (The starter would otherwise fail with ERROR ID 402.)")
            return
        # Pre-flight (v20.67): duplicate /INIVEL on the SAME node. Two INIVELs
        # that resolve to one node with DIFFERENT velocities are a last-write-
        # wins trap - the solver silently keeps one and you run at the wrong
        # speed (the 14000 vs 15000 mm/s case: a 15% energy error on a DOP
        # assessment, with nothing in the log). Halt and name both sources.
        _inivels = self._scan_inivel_targets(final_lines)
        # (a) collisions among the model's own INIVEL cards
        _node_to_iv = {}
        for iv in _inivels:
            for nd in iv["nodes"]:
                _node_to_iv.setdefault(nd, []).append(iv)
        _conflict_nodes = {nd: ivs for nd, ivs in _node_to_iv.items()
                           if len({iv["vel"] for iv in ivs}) > 1}
        if _conflict_nodes:
            nd0 = sorted(_conflict_nodes)[0]
            ivs = _conflict_nodes[nd0]
            listing = "; ".join(f"/INIVEL/TRA/{iv['id']} (grnod {iv['gid']}) "
                                f"V={iv['vel']}" for iv in ivs)
            self.log_msg("")
            self.log_msg(f"BUILD HALTED: node {nd0} is targeted by {len(ivs)} /INIVEL cards with "
                         f"DIFFERENT velocities - the solver keeps only one (last-write-wins), so "
                         f"the run speed is not what the model states.")
            self.log_msg(f"Cause: {listing}.")
            self.log_msg("Fix: delete the redundant *INITIAL CONDITIONS,TYPE=VELOCITY in PrePoMax "
                         "(or the extra /INIVEL) so each node has one velocity, then rebuild.")
            return

        # (b) the model already drives the node this build is about to drive.
        # Resolve the intended main node the same way the drive block does, and
        # halt if a model-side INIVEL already lands on it with a different value.
        _vmode_pf = self.rigid_vel_mode.get()
        if _vmode_pf == RBV_EXPL:
            _rv = self.rigid_vel.get().strip()
            _driven_vel = None
            if _rv:
                try:
                    _c = [float(x) for x in _rv.replace(",", " ").split()]
                    while len(_c) < 3:
                        _c.append(0.0)
                    _driven_vel = (_c[0], _c[1], _c[2])
                except ValueError:
                    _driven_vel = None
            # find the single RBODY main node (same rule the drive block enforces)
            _rb_mains = []
            _kk = 0
            while _kk < len(final_lines):
                _s = final_lines[_kk].strip()
                if _s.upper().startswith("/RBODY/"):
                    _mid = None
                    _seen = False
                    for _mm in range(_kk + 1, min(_kk + 10, len(final_lines))):
                        _t = final_lines[_mm].strip()
                        if not _t or _t.startswith("#"):
                            continue
                        if _t.startswith("/"):
                            break
                        if not _seen:
                            _seen = True; continue
                        try:
                            _mid = int(_t.split()[0])
                        except Exception:
                            pass
                        break
                    _rb_mains.append(_mid)
                _kk += 1
            if _driven_vel is not None and len(_rb_mains) == 1 and _rb_mains[0] is not None:
                _mn = _rb_mains[0]
                _clash = [iv for iv in _inivels
                          if _mn in iv["nodes"] and iv["vel"] != _driven_vel]
                if _clash:
                    listing = "; ".join(f"/INIVEL/TRA/{iv['id']} (grnod {iv['gid']}) "
                                        f"V={iv['vel']}" for iv in _clash)
                    self.log_msg("")
                    self.log_msg(f"BUILD HALTED: the impactor main node {_mn} already carries a "
                                 f"model-side /INIVEL, and Explicit velocity {_driven_vel} would add a "
                                 f"second one on the SAME node with a different value.")
                    self.log_msg(f"Cause: model card(s): {listing}; GUI would write V={_driven_vel}.")
                    self.log_msg("Fix: EITHER remove the *INITIAL CONDITIONS velocity from the "
                                 "PrePoMax model and keep driving from the GUI, OR set Impactor "
                                 "velocity mode to 'None (keep model)' and let the model's own "
                                 "INIVEL stand. Do not define both.")
                    return

        starter_rad_path = os.path.join(work_dir, f"{model_name}_0000.rad")
        with open(starter_rad_path, 'w') as f:
            f.writelines(final_lines)
            f.write("/GRNOD/PART/9999998\nUniversal_Nodes\n")
            p_str = "".join([f"{p:10d}" + ("\n" if (j+1)%8==0 else "") for j,p in enumerate(part_ids)])
            f.write(p_str.rstrip() + "\n/SURF/PART/EXT/9999999\nUniversal_Surface\n" + p_str.rstrip() + "\n")
            
            if self.gravity.get():
                # /GRAV: 7 fields in order (verified against a working deck) -
                # funct_ID, DIR (letter Z), skew, sensor, grnod_ID, Ascale_x,
                # Fscale_Y. Both scales = 1; the -9810 mm/s^2 magnitude is
                # carried in the /FUNCT Y-values, which also ramp gravity in
                # over the first 5% of tstop (soft-start, same idiom as the
                # velocity BC) rather than applying full g instantaneously.
                g_ramp = tstop * 0.05
                f.write("/GRAV/9999997\nGlobal_Gravity\n")
                f.write("#funct_ID       DIR   skew_ID sensor_ID  grnod_ID            Ascale_x            Fscale_Y\n")
                f.write(f"{9999997:>10}{'Z':>10}{0:>10}{0:>10}{9999998:>10}{1.0:>20.1f}{1.0:>20.1f}\n")
                f.write("/FUNCT/9999997\nGravity_Ramp\n")
                f.write(f"{0.0:>20.5f}{0.0:>20.5f}\n"
                        f"{g_ramp:>20.5f}{-9810.0:>20.5f}\n"
                        f"{tstop:>20.5f}{-9810.0:>20.5f}\n")
                self.log_msg(f"Gravity: /GRAV -Z, 9810 mm/s^2, ramped 0..{g_ramp:.5g}s "
                             f"(5% of tstop), grnod 9999998 (all parts).")
            
            # -------- GENERAL CONTACT: explicit mode (v20.63), one interface
            # over the universal groups. TYPE7 is byte-identical to the old
            # Self Contact card; TYPE19 adds automatic edge-to-edge; TYPE24 is
            # the constant-stiffness formulation with shell-edge contact.
            cmode = self.contact_mode.get()
            fric = float(self.fric.get())
            if cmode == CONTACT_T7:
                # Field 7 is Idel. Idel=1 removes dead segments AND non-connected
                # secondary nodes; Idel=0 leaves both in the interface. With any
                # element erosion active, Idel=0 is the direct cause of the
                # /DT/NODA/CST added-mass runaway (MESSAGE ID 207). So pin Idel to
                # the erosion state and say WHY in the log - never a silent 0.
                erode = self._erosion_active()
                idel = 1 if erode else 0
                f.write("/INTER/TYPE7/9999999\nGeneral_Self_Contact\n")
                f.write(f"{9999998:>10}{9999999:>10}{4:>10}{0:>10}{2:>10}{0:>10}{idel:>10}{0:>10}{0:>10}{0:>10}\n")
                f.write(f"{1.0:>20.1f}{fric:>20.4f}{0.15:>20.4f}{0.0:>20.1f}{0.0:>20.1f}\n")
                f.write(f"{6:>10}{0.0:>20.1f}{0.0:>20.1f}{0.0:>20.1f}{2:>10}\n0         0         0                 0.0         0\n0                 1.0         0         0\n\n")
                if erode:
                    self.log_msg(f"Contact: /INTER/TYPE7 universal (grnod 9999998 vs surf 9999999), "
                                 f"fric={fric}, Idel=1. CAUSE: failure model '{self.fail_model.get()}' "
                                 f"erodes elements; deleted segments and orphaned nodes MUST leave the "
                                 f"interface or /DT/NODA/CST diverges to a TOTAL MASS ERROR kill. "
                                 f"FIX applied automatically.")
                else:
                    self.log_msg(f"Contact: /INTER/TYPE7 universal (grnod 9999998 vs surf 9999999), "
                                 f"fric={fric}, Idel=0 (no erosion in the active failure model). "
                                 f"NOTE: if you later enable a deleting failure model, this switches "
                                 f"to Idel=1 to avoid the mass-error kill.")
            elif cmode == CONTACT_T19:
                # radioss2021 format: surf_s surf_m Istf Ithe Igap Iedge Ibag Idel Icurv
                # Single-surface self-impacting form: surf_IDs>0, surf_IDm=0.
                f.write("/INTER/TYPE19/9999999\nGeneral_Contact_T19\n")
                f.write(f"{9999999:>10}{0:>10}{4:>10}{0:>10}{1:>10}{1:>10}{0:>10}{2:>10}{0:>10}\n")
                # Fscale_gap, Gap_max
                f.write(f"{0.0:>20.1f}{0.0:>20.1f}\n")
                # Stmin, Stmax, %mesh_size, dtmin, Irem_gap, Irem_i2
                f.write(f"{0.0:>20.1f}{0.0:>20.1f}{0.0:>20.1f}{0.0:>20.1f}{0:>10}{0:>10}\n")
                # Stfac, Fric, Gapmin, Tstart, Tstop
                f.write(f"{1.0:>20.1f}{fric:>20.4f}{0.15:>20.4f}{0.0:>20.1f}{0.0:>20.1f}\n")
                # IBC(cols 8-10), Inacti, VISs, VISf, Bumult
                f.write(f"{'':>7}{0}{0}{0}{'':>20}{6:>10}{0.0:>20.1f}{0.0:>20.1f}{0.0:>20.1f}\n")
                # Ifric, Ifiltr, Xfreq, Iform, sens_ID
                f.write(f"{0:>10}{0:>10}{0.0:>20.1f}{0:>10}{0:>10}\n\n")
                self.log_msg(f"Contact: /INTER/TYPE19 single-surface (surf 9999999, Iedge=1 external "
                             f"shell edges, Idel=2, Inacti=6), fric={fric}.")
            elif cmode == CONTACT_T24:
                # radioss2021 format card 1: surf1 surf2 Istf [20 blank] Irem_i2 [10 blank] Idel
                f.write("/INTER/TYPE24/9999999\nGeneral_Contact_T24\n")
                f.write(f"{9999999:>10}{0:>10}{4:>10}{'':>20}{0:>10}{'':>10}{2:>10}\n")
                # grnd_IDs, [20 blank], Iedge, Edge_angle, Gap_max_s, Gap_max_m
                f.write(f"{0:>10}{'':>20}{1:>10}{0.0:>20.1f}{0.0:>20.1f}{0.0:>20.1f}\n")
                # Stmin, Stmax, Igap0, Ipen0, Ipen_max
                f.write(f"{0.0:>20.1f}{0.0:>20.1f}{0:>10}{0:>10}{0.0:>20.1f}\n")
                # Stfac, Fric, [20 blank], Tstart, Tstop
                f.write(f"{1.0:>20.1f}{fric:>20.4f}{'':>20}{0.0:>20.1f}{0.0:>20.1f}\n")
                # IBC(cols 8-10), [20 blank], Inacti, ViscS
                f.write(f"{'':>7}{0}{0}{0}{'':>20}{0:>10}{0.0:>20.1f}\n")
                # Ifric, Ifiltr, Xfreq, sens_ID
                f.write(f"{0:>10}{0:>10}{0.0:>20.1f}{'':>10}{0:>10}\n\n")
                self.log_msg(f"Contact: /INTER/TYPE24 single-surface (surf 9999999, constant stiffness, "
                             f"Iedge=1, Idel=2, default Edge_angle), fric={fric}.")
            else:
                self.log_msg("CONTACT WARNING: mode 'None' - no general contact written; parts only "
                             "interact through ties / model interfaces / rigid walls.")
            
            # -------- TIES: exactly one mechanism per build, chosen explicitly.
            # No silent fallback between modes; a mode with nothing to do warns
            # loudly and writes NO ties, so the deck never quietly gets a
            # different bonding scheme than the one selected.
            tmode = self.tie_mode.get()
            self.log_msg(f"Tie mode: {tmode}")
            auto_ties = []
            if tmode == TIE_AUTO:
                try:
                    auto_ties = self._parse_inp_ties(lines)
                except Exception as e:
                    self.log_msg(f"Auto-tie parse error: {e}")
                if not auto_ties:
                    self.log_msg("TIE WARNING: Auto (*TIE) mode is selected but the source .inp contains no "
                                 "*TIE definitions - NO ties written. Define ties in PrePoMax and re-export, "
                                 "or switch Tie Mode on the Build tab.")
            tie_text = getattr(self, "_tie_text", "").strip() if tmode == TIE_SCOPED else ""
            if tmode == TIE_SCOPED and not tie_text:
                self.log_msg("TIE WARNING: Scoped-pairs mode is selected but the Scoped Ties box is empty - "
                             "NO ties written.")

            if auto_ties:
                tie_id = 9990300
                made = 0
                for t in auto_ties:
                    if not t['slave_nodes'] or not t['master_segs']:
                        self.log_msg(f"Auto-tie: '{t['name']}' skipped (empty slave or master)."); continue
                    gid, sid, iid = tie_id, tie_id + 1, tie_id + 2
                    tie_id += 3
                    safe = "".join(ch if ch.isalnum() else "_" for ch in t['name'])[:40]
                    eff_tol = t['tol']
                    if eff_tol <= 0.0:
                        try: eff_tol = float(self.tie_dist.get())
                        except Exception: eff_tol = 0.0
                        if eff_tol > 0.0:
                            self.log_msg(f"Auto-tie '{t['name']}': no Position tolerance in INP; using Fallback dist = {eff_tol} mm.")
                        else:
                            self.log_msg(f"Auto-tie '{t['name']}': no tolerance and Fallback dist is 0 - set Fallback dist or add a Position tolerance in PrePoMax, or this tie catches nothing.")
                    f.write(f"/GRNOD/NODE/{gid}\nTieSlave_{safe}\n")
                    nd = t['slave_nodes']
                    f.write("".join(f"{x:10d}" + ("\n" if (k + 1) % 10 == 0 else "") for k, x in enumerate(nd)).rstrip() + "\n")
                    f.write(f"/SURF/SEG/{sid}\nTieMaster_{safe}\n")
                    for seg in t['master_segs']:
                        s = seg[:4] if len(seg) >= 4 else seg + [seg[-1]] * (4 - len(seg))
                        f.write("".join(f"{x:10d}" for x in s) + "\n")
                    f.write(f"/INTER/TYPE2/{iid}\nTie_{safe}\n")
                    f.write(f"{gid:>10}{sid:>10}{3:>10}{27:>10}{0:>10}{0:>10}{2:>10}{0:>10}{eff_tol:>10.3f}\n{2:>10}{0:>10}{0:>10}\n\n")
                    made += 1
                    self.log_msg(f"Auto-tie '{t['name']}': {len(nd)} slave nodes -> {len(t['master_segs'])} master segs, search={eff_tol} mm")
                self.log_msg(f"Auto-ties from model *TIE: {made} written.")
            elif tie_text:
                tie_id = 9990200
                made = 0
                for raw in tie_text.splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ">" not in line or ":" not in line:
                        self.log_msg(f"Tie: skipped '{line}' (format: secondary > master : distance).")
                        continue
                    lhs, dist_s = line.rsplit(":", 1)
                    sec_s, mas_s = lhs.split(">", 1)
                    try:
                        dist = float(dist_s.strip())
                    except Exception:
                        self.log_msg(f"Tie: bad distance in '{line}'."); continue
                    sec_pid, e1 = self._resolve_part(sec_s, part_ids, part_name_map)
                    mas_pid, e2 = self._resolve_part(mas_s, part_ids, part_name_map)
                    if sec_pid is None or mas_pid is None:
                        self.log_msg(f"Tie: '{line}' skipped ({(e1 or '')} {(e2 or '')})".strip() + "."); continue
                    if sec_pid == mas_pid:
                        self.log_msg(f"Tie: '{line}' skipped (secondary and master are the same part)."); continue
                    g_id, s_id, i_id = tie_id, tie_id + 1, tie_id + 2
                    tie_id += 3
                    f.write(f"/GRNOD/PART/{g_id}\nTieSec_{sec_pid}\n{sec_pid:>10}\n")
                    f.write(f"/SURF/PART/EXT/{s_id}\nTieMas_{mas_pid}\n{mas_pid:>10}\n")
                    f.write(f"/INTER/TYPE2/{i_id}\nTie_{sec_pid}_to_{mas_pid}\n")
                    f.write(f"{g_id:>10}{s_id:>10}{3:>10}{27:>10}{0:>10}{0:>10}{2:>10}{0:>10}{dist:>10.3f}\n")
                    f.write(f"{2:>10}{0:>10}{0:>10}\n\n")
                    made += 1
                    self.log_msg(f"Tie: part {sec_pid} -> {mas_pid} (master), dsearch={dist} mm [scoped].")
                self.log_msg(f"Scoped ties written: {made}.")
            elif tmode == TIE_GLOBAL:
                try:
                    td = float(self.tie_dist.get() or 0)
                except Exception:
                    td = 0.0
                if td > 0.0:
                    f.write("/INTER/TYPE2/9999998\nUniversal_Global_Tie\n")
                    f.write(f"{9999998:>10}{9999999:>10}{3:>10}{27:>10}{0:>10}{0:>10}{2:>10}{0:>10}{td:>10.3f}\n")
                    f.write(f"{2:>10}{0:>10}{0:>10}\n\n")
                    self.log_msg(f"Global tie written: any node may bond to any surface within {td} mm.")
                else:
                    self.log_msg("TIE WARNING: Single-global mode is selected but Tie dist is 0 - NO tie written.")

            if "Rigid Floor" in self.test_mode.get():
                f.write("/RWALL/PLANE/1\nInfinite_Rigid_Floor\n" + f"{0.0:>20.4f}{0.0:>20.4f}{float(self.floor_z.get()):>20.4f}\n" + f"{0.0:>20.4f}{0.0:>20.4f}{1.0:>20.4f}\n" + f"{float(self.fric.get()):>20.4f}{0.0:>20.4f}{0.0:>20.4f}{0.0:>20.4f}\n10        \n{9999998:>10}\n\n")
                  
            # -------- IMPACTOR VELOCITY: written onto the MAIN node of the
            # model's /RBODY (the PrePoMax reference point). v20.59 removed
            # rigid-body injection: the model owns the rigid body, the build
            # only drives it. Explicit mode, no silent fallback; the deck's
            # /RBODY and /INIVEL counts are always logged.
            vmode = self.rigid_vel_mode.get()
            rbodies = []  # (rbid, title, main_node_id)
            k = 0
            while k < len(final_lines):
                s = final_lines[k].strip()
                if s.upper().startswith("/RBODY/"):
                    parts_hdr = s.split("/")
                    rbid = parts_hdr[2] if len(parts_hdr) > 2 else "?"
                    title, main_id, seen_title = "", None, False
                    for m in range(k + 1, min(k + 10, len(final_lines))):
                        t = final_lines[m].strip()
                        if not t or t.startswith("#"):
                            continue
                        if t.startswith("/"):
                            break
                        if not seen_title:
                            title, seen_title = t, True
                            continue
                        try:
                            main_id = int(t.split()[0])
                        except Exception:
                            pass
                        break
                    rbodies.append((rbid, title, main_id))
                k += 1
            n_inivel = sum(1 for l in final_lines if l.strip().upper().startswith("/INIVEL"))
            self.log_msg(f"Impactor velocity mode: {vmode}  (deck contains {len(rbodies)} /RBODY "
                         f"and {n_inivel} /INIVEL from the model)")
            if vmode == RBV_EXPL:
                vx = vy = vz = None
                rv = self.rigid_vel.get().strip()
                if not rv:
                    self.log_msg("RIGID WARNING: Explicit velocity is selected but the Vx Vy Vz field "
                                 "is empty - NO velocity written; the impactor will not move on its own.")
                else:
                    try:
                        comps = [float(x) for x in rv.replace(",", " ").split()]
                        while len(comps) < 3: comps.append(0.0)
                        vx, vy, vz = comps[0], comps[1], comps[2]
                    except Exception:
                        self.log_msg(f"RIGID WARNING: could not parse Vx Vy Vz '{rv}' (expected up to "
                                     f"3 numbers) - NO velocity written; fix the field and rebuild.")
                sel = None
                if vx is not None:
                    sel, why = self._select_target_rbody(rbodies, self.rigid_rp_target.get())
                    if sel is None:
                        self.log_msg(f"RIGID WARNING: {why} - NO velocity written. (Define the "
                                     f"impactor rigid body in the model, or set 'Target RP' to the "
                                     f"/RBODY you mean.)")
                        vx = None
                if vx is not None:
                    rbid, title, main_id = sel
                    if n_inivel:
                        self.log_msg(f"RIGID WARNING: the deck already contains {n_inivel} /INIVEL "
                                     f"card(s). The main-node velocity is still written (a rigid body "
                                     f"moves via its MAIN node), but remove the model-side velocity if "
                                     f"this is unintended - double definitions are the failure mode "
                                     f"v20.59 exists to prevent.")
                    R_VGRN, R_IVID = 9990004, 9990005
                    f.write(f"/GRNOD/NODE/{R_VGRN}\nRigid_Main_Node\n{main_id:>10}\n")
                    f.write(f"/INIVEL/TRA/{R_IVID}\nRigid_Impactor_Velocity\n")
                    f.write(f"{vx:>20.6f}{vy:>20.6f}{vz:>20.6f}{R_VGRN:>10}{0:>10}\n")
                    self.log_msg(f"Impactor velocity ({vx}, {vy}, {vz}) written on /RBODY/{rbid} "
                                 f"('{title}') main node {main_id}.")
            elif vmode in (RBV_PROFILE, RBV_PROFILE_F):
                # v20.64: drive the single /RBODY main node with a smooth
                # load-hold-unload profile - imposed displacement (/IMPDISP)
                # or force (/CLOAD). Same single-/RBODY requirement as Explicit.
                # Card layouts verified against the OpenRadioss readers:
                # /IMPDISP shares the /IMPVEL layout; /CLOAD has an extra
                # Itypfun column (funct Dir skew sensor grnod Itypfun Asc Fsc).
                is_force = (vmode == RBV_PROFILE_F)
                ok = True
                sel, why = self._select_target_rbody(rbodies, self.rigid_rp_target.get())
                if sel is None:
                    self.log_msg(f"RIGID WARNING: profile drive - {why}, NO card written.")
                    ok = False
                if ok:
                    try:
                        peak = float(self.lhu_peak.get())
                        ru = float(self.lhu_rampup.get()); hd = float(self.lhu_hold.get())
                        rd = float(self.lhu_rampdn.get()); st = float(self.lhu_settle.get())
                        npr = int(float(self.lhu_npramp.get()))
                        ts_c, vs_c = self._build_lhu_curve(ru, hd, rd, st, self.lhu_easing.get(), npr)
                    except ValueError as e:
                        self.log_msg(f"RIGID WARNING: profile inputs invalid ({e}) - NO card written.")
                        ok = False
                if ok:
                    rbid, title, main_id = sel
                    dir_map = {"X": 1, "Y": 2, "Z": 3}
                    d_str = self.lhu_dir.get() if self.lhu_dir.get() in dir_map else "Z"
                    try:
                        run_tstop = float(self.tstop.get())
                    except Exception:
                        run_tstop = ts_c[-1]
                    profile_total = ts_c[-1]
                    if run_tstop > profile_total + 1e-12:
                        ts_c = ts_c + [run_tstop]; vs_c = vs_c + [0.0]
                        self.log_msg(f"Profile: run Tstop {run_tstop:g}s > profile {profile_total:g}s - "
                                     f"trailing zero added; indenter {'unloaded' if is_force else 'stays retracted'} "
                                     f"to the end.")
                    elif run_tstop < profile_total - 1e-12:
                        self.log_msg(f"RIGID WARNING: run Tstop {run_tstop:g}s < profile total "
                                     f"{profile_total:g}s - the profile will be TRUNCATED (unload/settle "
                                     f"cut off). Raise Time (Tstop) to >= {profile_total:g}s.")
                    imp_tstop = max(run_tstop, profile_total)
                    if n_inivel:
                        self.log_msg(f"RIGID WARNING: the deck already contains {n_inivel} /INIVEL "
                                     f"card(s) from the model; the profile card is still written on "
                                     f"the main node. Remove the model-side kinematics if unintended.")
                    R_LGRN, R_LFCT, R_LIMP = 9990006, 9990007, 9990008
                    f.write(f"/GRNOD/NODE/{R_LGRN}\nRigid_Main_Node\n{main_id:>10}\n")
                    f.write(f"/FUNCT/{R_LFCT}\nLHU_Profile_Shape\n")
                    for tt, vv in zip(ts_c, vs_c):
                        f.write(f"{tt:>20.9g}{vv:>20.9g}\n")
                    if is_force:
                        # /CLOAD: funct_IDT Dir skew_ID sensor_ID grnod_ID Itypfun Ascalex Fscaley
                        f.write(f"/CLOAD/{R_LIMP}\nRigid_Impactor_LHU_Force\n")
                        f.write(f"{R_LFCT:>10}{d_str:>10}{0:>10}{0:>10}{R_LGRN:>10}{0:>10}"
                                f"{1.0:>20.5f}{peak:>20.6f}\n")
                        self.log_msg(f"Profile /CLOAD on /RBODY/{rbid} ('{title}') main node {main_id}: "
                                     f"peak force {peak} in {d_str}, shape {self.lhu_easing.get()}, "
                                     f"ramp {ru}/hold {hd}/ramp {rd}/settle {st}s ({len(ts_c)} /FUNCT points). "
                                     f"Force control - watch KE/IE for overshoot.")
                    else:
                        # /IMPDISP: fct Dir 0 0 grnod ; Ascale Fscale Tstart Tstop
                        f.write(f"/IMPDISP/{R_LIMP}\nRigid_Impactor_LHU\n")
                        f.write(f"{R_LFCT:>10}{d_str:>10}{0:>10}{0:>10}{R_LGRN:>10}\n")
                        f.write(f"{1.0:>20.5f}{peak:>20.6f}{0.0:>20.5f}{imp_tstop:>20.5f}\n")
                        self.log_msg(f"Profile /IMPDISP on /RBODY/{rbid} ('{title}') main node {main_id}: "
                                     f"peak {peak}mm in {d_str}, shape {self.lhu_easing.get()}, "
                                     f"ramp {ru}/hold {hd}/ramp {rd}/settle {st}s "
                                     f"({len(ts_c)} /FUNCT points, {self.lhu_dir.get()}-dir).")
            else:
                self.log_msg("Impactor velocity: None - nothing written; the deck keeps the model's "
                             "kinematics as-is.")

            f.write("/END\n")

        try:
            n_frames = int(float(self.anim_frames.get()))
            if n_frames < 1:
                n_frames = 100
        except Exception:
            n_frames = 100
        anim_dt = tstop / n_frames

        # v20.65: mass-scaling floor. DTmin > 0 activates OpenRadioss constant-
        # timestep mass scaling (mass added to sub-floor nodes); DTmin = 0 keeps
        # the raw mesh-limited timestep (pre-v20.65 behaviour).
        try:
            dt_min = float(self.dt_min.get())
            if dt_min < 0:
                dt_min = 0.0
        except Exception:
            dt_min = 0.0
        if dt_min > 0:
            n_est = tstop / dt_min
            self.log_msg(f"Mass scaling ON: /DT/NODA/CST DTmin={dt_min:g}s - solver adds mass to hold "
                         f"the timestep at {dt_min:g}s (~{n_est:,.0f} steps over Tstop {tstop:g}s). "
                         f"This is solver nodal mass, NOT a density change. WATCH the added-mass % and "
                         f"KE/IE in the solver output; if either climbs, lower DTmin or coarsen the mesh.")
        else:
            self.log_msg("Mass scaling OFF (Min dt = 0): the run uses the raw mesh-limited timestep. "
                         "For a sub-mm mesh this can be millions of steps - set Min dt to a target "
                         "timestep (e.g. 10-30x the natural dt) to make a quasi-static run affordable.")

        # v20.67: interface-timestep backstop. When elements erode, a node can
        # lose every connected element while a contact still owns it; /DT/NODA/CST
        # then scales its mass toward infinity to hold the step (MESSAGE ID 207).
        # /DT/INTER/DEL instead REMOVES such a node from the interface once its
        # contact timestep falls below dt_int_min - a bounded, physical exit that
        # complements TYPE7 Idel=1. Floor sits well below the working step: an
        # order below the mass-scaling target when set, else a small absolute value.
        erode_engine = self._erosion_active()
        if erode_engine:
            dt_int_min = (dt_min / 100.0) if dt_min > 0 else 1.0e-8
            self.log_msg(f"Engine: /DT/INTER/DEL backstop written (Tsc=0.67, dtmin={dt_int_min:g}s). "
                         f"A node whose CONTACT timestep drops below this is dropped from the "
                         f"interface instead of being mass-scaled to a TOTAL MASS ERROR kill. "
                         f"Pairs with TYPE7 Idel=1; active because the failure model erodes elements.")
            # v20.69: element-level erosion backstop. /DT/INTER/DEL and TYPE7
            # Idel=1 only remove a collapsing node from CONTACT; the degenerate
            # SHELL itself still forces /DT/NODA/CST to pile unbounded mass onto
            # its nodes (the 2e+76 kg, MESSAGE ID 205/207 kill). /DT/NODA/DEL is
            # rejected by the engine reader, so the deletion has to be at the
            # element level: /DT/SHELL/DEL (and /DT/SH3N/DEL for tri shells)
            # DELETE a shell once its own timestep drops below the floor, before
            # nodal scaling can run away. Floor at dt_min/10 caps a survivor at
            # ~100x added mass; anything worse erodes. Sits an order ABOVE the
            # interface floor so shells are culled first. When mass scaling is
            # off (dt_min=0) it still frees a collapsed shell that would
            # otherwise crush the raw timestep; a small absolute floor is used.
            dt_shell_min = (dt_min / 10.0) if dt_min > 0 else 1.0e-7
            self.log_msg(f"Engine: /DT/SHELL/DEL + /DT/SH3N/DEL erosion backstop written "
                         f"(Tsc=0.9, dtmin={dt_shell_min:g}s). A shell whose OWN timestep falls "
                         f"below this is deleted instead of mass-scaled to infinity - the "
                         f"element-level twin of /DT/INTER/DEL. Healthy shells sit far above it, "
                         f"so only already-ruptured degenerate elements erode; check the eroded "
                         f"mass in the output stays small vs total model mass.")

        with open(os.path.join(work_dir, f"{model_name}_0001.rad"), 'w') as f:
            f.write(f"#RADIOSS ENGINE\n/RUN/{model_name}/1\n{tstop}\n/DT/NODA/CST\n{0.9:>20.4f}{dt_min:>20.6g}\n")
            if erode_engine:
                f.write(f"/DT/INTER/DEL\n{0.67:>20.4f}{dt_int_min:>20.6g}\n")
                f.write(f"/DT/SHELL/DEL\n{0.9:>20.4f}{dt_shell_min:>20.6g}\n")
                f.write(f"/DT/SH3N/DEL\n{0.9:>20.4f}{dt_shell_min:>20.6g}\n")
            f.write(f"/ANIM/DT\n0.0 {anim_dt}\n")
            
            # --- Standard Elemental Averages ---
            f.write("/ANIM/VECT/VEL\n/ANIM/VECT/DISP\n/ANIM/VECT/CONT\n/ANIM/ELEM/VONM\n/ANIM/ELEM/EPSP\n/ANIM/ELEM/ENERGY\n/ANIM/ELEM/HOURG\n")
            
            # --- Integration Point Data (Through-Thickness) ---
            f.write("/ANIM/SHELL/EPSP/ALL\n/ANIM/SHELL/TENS/ALL\n")
            # --- Strain TENSOR at surfaces + membrane (for principal-strain post) ---
            # Requires Istrain=1 in /PROP/SHELL (enforced by _enable_shell_istrain on
            # the starter). UPPER/LOWER are the two surfaces (read the tension face for
            # CC02); MEMB is the mid-plane membrane value (CC01). Max principal strain
            # is computed from these tensor components in ParaView.
            f.write("/ANIM/SHELL/TENS/STRAIN/MEMB\n/ANIM/SHELL/TENS/STRAIN/UPPER\n/ANIM/SHELL/TENS/STRAIN/LOWER\n")
            # --- Solid strain TENSOR (v20.72) ---
            # The shell-only list left SOLID decks with no total-strain tensor
            # in the animation, so the eps1 session had nothing to colour by
            # (only the scalar /ANIM/ELEM/EPSP survived). /ANIM/BRICK/TENS/
            # STRAIN writes the 3D tensor for every solid element; the
            # element-agnostic eps1 filter picks it up as eps1_solid. Harmless
            # on a pure-shell deck (no bricks -> no output).
            f.write("/ANIM/BRICK/TENS/STRAIN\n")
            f.write(f"/TH/TITLE\n/TFILE\n{tstop/1000.0}\n/END\n")
        try: os.remove(safe_inp_file); os.remove(rad_file_safe)
        except: pass

        # Move the finished decks from the local build folder to the destination
        # (the Z: share in server mode). Only two files cross the network now.
        # v20.46: with 'Subfolder per build' the destination is a fresh
        # <target>/<MODEL_bNN>/ so decks, the settings report and all solver
        # output for one build live together and can be deleted as one unit.
        deck_dir = os.path.join(target_dir, model_name) if self.build_subdirs.get() else target_dir
        final_rad_file = os.path.join(deck_dir, f"{model_name}_0000.rad")
        try:
            if os.path.normpath(deck_dir) != os.path.normpath(work_dir):
                os.makedirs(deck_dir, exist_ok=True)
                self.log_msg(f"Copying decks to {deck_dir} ...")
                for fn in (f"{model_name}_0000.rad", f"{model_name}_0001.rad"):
                    shutil.copy2(os.path.join(work_dir, fn), os.path.join(deck_dir, fn))
                self.log_msg(f"Copied decks to {deck_dir}")
        except Exception as e:
            self.log_msg(f"Error copying decks to {deck_dir}: {e}")
            self.log_msg(f"(The built decks are still available locally in {work_dir}.)")
            return
        finally:
            # Remove the local build scratch only if we successfully copied out.
            if os.path.normpath(deck_dir) != os.path.normpath(work_dir) and os.path.exists(final_rad_file):
                shutil.rmtree(work_dir, ignore_errors=True)

        self.log_msg(f"SUCCESS: Model Built at {final_rad_file}")
        self.rad_target.set(final_rad_file.replace('\\', '/'))
        self._write_settings_txt(deck_dir, model_name)
        if self.purge_prev.get():
            self._purge_previous_builds(target_dir, base_name, bno + 1)
        self._record_build(target_dir, model_name,
                           deck_rel=os.path.relpath(final_rad_file, target_dir).replace("\\", "/"))
        self.save_state()
        self._build_done(final_rad_file, deck_dir, model_name)


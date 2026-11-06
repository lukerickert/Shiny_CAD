#!/usr/bin/env python3
"""
job_audit.py  -  job auditor
============================================================
Walks a runs tree, and for every job (each *_0000*.rad it finds) reads the
ACTUAL artifacts on disk - starter deck, engine deck, settings report, pv
manifest and converted VTK - and reports the diagnostic-critical facts side by
side. Ground truth from the files, NOT the GUI's intended settings, so it tells
you whether a result is missing something because of a *setting* or because of
*how that particular job was built*.

Answers at a glance, per job:
  - Will it produce max principal strain?  (Istrain on props + strain ANIM cards
    in the engine + tensor arrays in the VTK)
  - Is any /RBODY malformed?  (the 9-field / grnd_ID!=0 check = Error 274 risk)
  - What contact / tie / material / mass-scaling / Tstop was actually used?

Usage:
    python job_audit.py <root_folder> [-o job_audit.txt]
    python job_audit.py .            # audit everything under the current folder

Writes <out>.txt (human readable) and <out>.csv (one row per job) next to cwd.
Pure stdlib; runs anywhere Python 3 does, with or without the GUI.
"""
import os, sys, re, csv, glob, json, argparse
from datetime import datetime

STRAIN_CARDS = ("/ANIM/SHELL/TENS/STRAIN/MEMB",
                "/ANIM/SHELL/TENS/STRAIN/UPPER",
                "/ANIM/SHELL/TENS/STRAIN/LOWER")


def _read(path):
    try:
        with open(path, "r", errors="ignore") as fh:
            return fh.read().splitlines()
    except Exception:
        return []


def _job_from_starter(fname):
    """CASE_x_0000.rad or CASE_x_0000_stripped.rad -> CASE_x"""
    base = os.path.basename(fname)
    m = re.match(r"(.+?)_0000(?:_stripped)?\.rad$", base, re.I)
    return m.group(1) if m else None


def audit_starter(path):
    """props/Istrain, rigid bodies (274 guard), contacts, materials, parts."""
    lines = _read(path)
    r = {"props": 0, "istrain_bad": [], "rbody": 0, "rbody_bad": [],
         "inter": [], "mats": [], "parts": 0, "stripped": "_stripped" in path.lower()}
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("/PART/"):
            r["parts"] += 1
        elif s.startswith("/MAT/"):
            r["mats"].append(s.split("/")[2] if len(s.split("/")) > 2 else s)
        elif s.startswith("/PROP/SHELL"):
            r["props"] += 1
            pid = s.rsplit("/", 1)[-1]
            # find the "N Istrain ..." data line: it is the first non-comment
            # data line after the hm/hf/hr/dm/dn line. Simplest robust approach:
            # scan the next ~8 lines for the one whose comment header mentions
            # Istrain, then read the following data line.
            for k in range(i, min(i + 10, len(lines))):
                if "Istrain" in lines[k]:
                    dat = lines[k + 1].split() if k + 1 < len(lines) else []
                    if len(dat) >= 2 and dat[1] != "1":
                        r["istrain_bad"].append(f"{pid}(Istrain={dat[1]})")
                    break
        elif s.startswith("/RBODY/"):
            r["rbody"] += 1
            rid = s.rsplit("/", 1)[-1]
            # main line = first non-comment, non-title data line after the title
            j = i + 2
            while j < len(lines) and (not lines[j].strip() or lines[j].lstrip().startswith("#")):
                j += 1
            fields = lines[j].split() if j < len(lines) else []
            # Two valid shapes, both 9 fields:
            #   rigidify        -> grnd_ID (f6) != 0, Mass (f5) may be 0 (ICoG=1)
            #   concentrated    -> grnd_ID (f6) == 0, Mass (f5) != 0 (free node +
            #                       explicit inertia line follows). NOT malformed.
            if len(fields) != 9:
                r["rbody_bad"].append(f"{rid}({len(fields)}fields)")
            elif fields[5] == "0":
                mass_ok = False
                try:
                    mass_ok = float(fields[4]) != 0.0
                except ValueError:
                    mass_ok = False
                if not mass_ok:
                    r["rbody_bad"].append(f"{rid}(grnd=0,Mass=0)")
        elif s.startswith("/INTER/TYPE"):
            typ = s.split("/")[2] if len(s.split("/")) > 2 else "?"
            idel = "?"
            # TYPE7 first data line: grnd surf Istf Ithe Igap Ibag Idel ...
            if typ == "TYPE7":
                j = i + 2
                while j < len(lines) and (not lines[j].strip() or lines[j].lstrip().startswith("#")):
                    j += 1
                f = lines[j].split() if j < len(lines) else []
                if len(f) >= 7:
                    idel = f"Idel={f[6]}"
            r["inter"].append(f"{typ}{('/' + idel) if idel != '?' else ''}")
        i += 1
    return r


def audit_engine(path):
    lines = _read(path)
    text = "\n".join(lines)
    r = {"exists": bool(lines), "tstop": None, "anim_dt": None,
         "strain_cards": [c for c in STRAIN_CARDS if c in text],
         "erosion_dt": bool(re.search(r"/DT/(INTER|SHELL|SH3N)/DEL", text)),
         "dt_noda": None}
    m = re.search(r"/RUN/[^\n]+\n\s*([0-9.eE+-]+)", text)
    if m:
        r["tstop"] = m.group(1)
    m = re.search(r"/DT/NODA/CST\s*\n\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)", text)
    if m:
        r["dt_noda"] = f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"/ANIM/DT\s*\n\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)", text)
    if m:
        r["anim_dt"] = m.group(2)
    return r


def audit_vtk(folder, job):
    """Pick a representative converted VTK and check for the tensor + erosion."""
    cands = sorted(glob.glob(os.path.join(folder, f"{job}_*.vtk"))) or \
            sorted(glob.glob(os.path.join(folder, f"{job}A*.vtk")))
    if not cands:
        return {"vtk": None}
    vtk = cands[-1]
    hdr_ok = strain = erosion = False
    try:
        with open(vtk, "rb") as fh:
            hdr_ok = fh.read(5) == b"# vtk"
        with open(vtk, "r", errors="ignore") as fh:
            body = fh.read()
        strain = "2DELEM_Strain_(upper)" in body
        erosion = "EROSION_STATUS" in body
    except Exception:
        pass
    return {"vtk": os.path.basename(vtk), "hdr_ok": hdr_ok,
            "strain": strain, "erosion": erosion}


def audit_settings(folder, job):
    """Pull a few key intended-selections from <job>_settings.txt if present."""
    path = os.path.join(folder, f"{job}_settings.txt")
    if not os.path.isfile(path):
        return {}
    txt = "\n".join(_read(path))
    keys = {}
    for label, pat in (("fail_model", r"Fail(?:ure)? model[:\s]+([^\n]+)"),
                       ("contact", r"Contact[^\n:]*:\s*([^\n]+)"),
                       ("tie", r"Tie[^\n:]*:\s*([^\n]+)"),
                       ("rigidify", r"Rigidif[^\n:]*:\s*([^\n]+)"),
                       ("version", r"Script\s*:\s*([^\n]+)")):
        m = re.search(pat, txt, re.I)
        if m:
            keys[label] = m.group(1).strip()[:60]
    return keys


def strain_verdict(st, en, vtk):
    if not en["exists"]:
        return "UNKNOWN  - engine _0001.rad not found (cannot confirm strain cards)"
    if len(en["strain_cards"]) < 3:
        miss = [c.split("/")[-1] for c in STRAIN_CARDS if c not in en["strain_cards"]]
        return f"NO STRAIN - engine deck missing {','.join(miss)} (rebuild via current workspace_build.py, or add the 3 cards to _0001.rad and re-run the engine)"
    if st["istrain_bad"]:
        return f"NO STRAIN - Istrain!=1 on prop(s) {','.join(st['istrain_bad'])}"
    if vtk.get("vtk") and not vtk.get("strain"):
        return "NO STRAIN - cards present but tensor absent in VTK (re-run anim_to_vtk; check A-file content)"
    if vtk.get("vtk") and vtk.get("strain"):
        return "STRAIN OK - tensor arrays present in VTK"
    return "STRAIN LIKELY OK - cards + Istrain present (no VTK converted yet to confirm)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="folder to walk for jobs")
    ap.add_argument("-o", "--out", default="job_audit", help="output basename")
    args = ap.parse_args()

    starters = []
    for dp, _, fns in os.walk(args.root):
        for fn in fns:
            if re.match(r".+_0000(?:_stripped)?\.rad$", fn, re.I):
                starters.append(os.path.join(dp, fn))
    starters.sort()

    rows, blocks = [], []
    for sp in starters:
        folder = os.path.dirname(sp)
        job = _job_from_starter(sp)
        if not job:
            continue
        st = audit_starter(sp)
        ep = os.path.join(folder, f"{job}_0001.rad")
        if not os.path.isfile(ep):
            alt = glob.glob(os.path.join(folder, f"{job}_0001*.rad"))
            ep = alt[0] if alt else ep
        en = audit_engine(ep)
        vtk = audit_vtk(folder, job)
        cfg = audit_settings(folder, job)
        sv = strain_verdict(st, en, vtk)
        rv = ("RBODY OK" if not st["rbody_bad"]
              else f"RBODY MALFORMED (Error 274 risk): {'; '.join(st['rbody_bad'])} - rebuild via fixed workspace_build.py")

        rows.append({
            "job": job, "folder": folder, "stripped": st["stripped"],
            "parts": st["parts"], "props": st["props"],
            "istrain_all_1": not st["istrain_bad"],
            "rbody": st["rbody"], "rbody_ok": not st["rbody_bad"],
            "contacts": " ".join(st["inter"]), "mats": " ".join(st["mats"]),
            "engine_found": en["exists"], "tstop": en["tstop"],
            "dt_noda": en["dt_noda"], "erosion_dt": en["erosion_dt"],
            "strain_cards": len(en["strain_cards"]),
            "vtk": vtk.get("vtk"), "vtk_strain": vtk.get("strain"),
            "vtk_erosion": vtk.get("erosion"),
            "fail_model": cfg.get("fail_model", ""), "contact_set": cfg.get("contact", ""),
            "tie_set": cfg.get("tie", ""), "rigidify_set": cfg.get("rigidify", ""),
            "built_by": cfg.get("version", ""),
            "STRAIN_VERDICT": sv, "RBODY_VERDICT": rv,
        })

        B = []
        B.append("=" * 92)
        B.append(f"JOB: {job}")
        B.append(f"  folder      : {folder}")
        if st["stripped"]:
            B.append("  (starter is a _stripped deck - geometry removed; card content still valid to audit)")
        B.append(f"  starter     : {st['parts']} parts, {st['props']} shell props, "
                 f"Istrain all=1: {'YES' if not st['istrain_bad'] else 'NO -> ' + ','.join(st['istrain_bad'])}")
        B.append(f"  materials   : {', '.join(st['mats']) or '(none)'}")
        B.append(f"  contacts    : {', '.join(st['inter']) or '(none)'}")
        B.append(f"  rigid bodies: {st['rbody']}  ->  {rv}")
        if en["exists"]:
            B.append(f"  engine      : Tstop={en['tstop']}  /DT/NODA/CST={en['dt_noda']}  "
                     f"ANIM_DT={en['anim_dt']}  erosion /DT={'yes' if en['erosion_dt'] else 'no'}")
            B.append(f"  strain cards: {len(en['strain_cards'])}/3 "
                     f"({'all present' if len(en['strain_cards']) == 3 else 'MISSING ' + ','.join(c.split('/')[-1] for c in STRAIN_CARDS if c not in en['strain_cards'])})")
        else:
            B.append("  engine      : _0001.rad NOT FOUND")
        if vtk.get("vtk"):
            B.append(f"  vtk sample  : {vtk['vtk']}  header_ok={vtk['hdr_ok']}  "
                     f"strain_tensor={'YES' if vtk['strain'] else 'NO'}  erosion={'yes' if vtk['erosion'] else 'no'}")
        else:
            B.append("  vtk sample  : (none converted)")
        if cfg:
            B.append(f"  settings.txt: " + "  ".join(f"{k}={v}" for k, v in cfg.items()))
        B.append("")
        B.append(f"  >> MAX PRINCIPAL STRAIN : {sv}")
        B.append(f"  >> RIGID BODY           : {rv}")
        blocks.append("\n".join(B))

    txt_path = os.path.abspath(args.out + ".txt")
    csv_path = os.path.abspath(args.out + ".csv")
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write("JOB AUDIT\n")
        fh.write(f"Generated : {datetime.now().isoformat(timespec='seconds')}\n")
        fh.write(f"Root      : {os.path.abspath(args.root)}\n")
        fh.write(f"Jobs found: {len(rows)}\n\n")
        fh.write("\n".join(blocks))
        fh.write("\n" + "=" * 92 + "\nEND\n")
    if rows:
        with open(csv_path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f"Audited {len(rows)} job(s).")
    print(f"  {txt_path}")
    print(f"  {csv_path}")


if __name__ == "__main__":
    main()

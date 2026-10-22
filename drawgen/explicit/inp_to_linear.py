#!/usr/bin/env python3
"""
inp_to_linear.py  -  downgrade a CalculiX/PrePoMax .inp from 2nd-order
                     (quadratic) to 1st-order (linear) elements so inp2rad
                     (and OpenRadioss, which is first-order only) can read it.

What it does
------------
- Rewrites every *ELEMENT block: quadratic TYPE -> linear TYPE, and the
  connectivity is truncated to the corner nodes (midside nodes dropped).
  Handles multi-line (wrapped) element records.
- Prunes nodes that, after the downgrade, are referenced by NO element. This
  matters for explicit: an orphaned free node with no mass can drive
  /DT/NODA/CST to zero and stall the run - leftover midside nodes are exactly
  that. (Disable with --keep-nodes.)
- Filters *NSET / *ELSET node lists so any dropped midside node is removed
  from node sets too (a linear-mesh BC belongs on corner nodes anyway).
  Element sets and element-face surfaces are untouched (element ids unchanged).

Not converted (passed through unchanged, with a warning): any TYPE not in the
map below. Already-linear meshes pass through cleanly (nothing to do).

Usage
-----
    python inp_to_linear.py model.inp                 # -> model_linear.inp
    python inp_to_linear.py model.inp -o out.inp
    python inp_to_linear.py model.inp --keep-nodes    # don't prune orphans
    python inp_to_linear.py --selftest                # build+convert a tiny mesh

Pure stdlib.
"""
import sys, re, argparse

# quadratic type -> (linear type, corner-node count)
MAP = {
    "C3D10":  ("C3D4",  4),  "C3D10T": ("C3D4",  4),
    "C3D20":  ("C3D8",  8),  "C3D20R": ("C3D8R", 8),
    "C3D15":  ("C3D6",  6),
    "S8":     ("S4",    4),  "S8R":    ("S4R",   4),
    "S6":     ("S3",    3),  "STRI65": ("S3",    3),
    "CPS8":   ("CPS4",  4),  "CPS6":   ("CPS3",  3),
    "CPE8":   ("CPE4",  4),  "CPE6":   ("CPE3",  3),
    "CAX8":   ("CAX4",  4),  "CAX6":   ("CAX3",  3),
    "B32":    ("B31",   2),  "B32R":   ("B31R",  2),
}
# full node count per quadratic type (to stream wrapped records correctly)
FULL = {"C3D10": 10, "C3D10T": 10, "C3D20": 20, "C3D20R": 20, "C3D15": 15,
        "S8": 8, "S8R": 8, "S6": 6, "STRI65": 6, "CPS8": 8, "CPS6": 6,
        "CPE8": 8, "CPE6": 6, "CAX8": 8, "CAX6": 6, "B32": 3, "B32R": 3}


def _kw(line):
    return line.lstrip().startswith("*") and not line.lstrip().startswith("**")


def _param(header, name):
    m = re.search(name + r"\s*=\s*([^,\s]+)", header, re.I)
    return m.group(1) if m else None


def convert(text, prune=True):
    lines = text.splitlines()
    out, i, n = [], 0, len(lines)
    stats = {"converted": {}, "passed": set(), "elem_nodes": set(),
             "orphans": 0, "nsets_filtered": 0}

    # ---- pass 1: rewrite elements, collect surviving (corner) node ids ------
    while i < n:
        line = lines[i]
        if _kw(line) and line.lstrip().upper().startswith("*ELEMENT"):
            header = line
            etype = (_param(header, "TYPE") or "").upper()
            i += 1
            # gather this block's data lines
            data = []
            while i < n and not _kw(lines[i]):
                data.append(lines[i]); i += 1
            if etype in MAP:
                lin_type, keep = MAP[etype]
                full = FULL[etype]
                toks = []
                for dl in data:
                    if dl.strip().startswith("**") or not dl.strip():
                        continue
                    toks += [t for t in dl.replace(",", " ").split() if t != ""]
                # stream records of (1 id + full nodes)
                rec = 1 + full
                new_header = re.sub(r"(TYPE\s*=\s*)[^,\s]+", r"\g<1>" + lin_type,
                                    header, flags=re.I)
                out.append(new_header)
                k = 0
                cnt = 0
                while k + rec <= len(toks):
                    eid = toks[k]
                    nodes = toks[k + 1:k + 1 + keep]      # corner nodes only
                    for nd in nodes:
                        stats["elem_nodes"].add(nd)
                    out.append(eid + ", " + ", ".join(nodes))
                    k += rec
                    cnt += 1
                if k != len(toks):
                    sys.stderr.write(
                        f"WARNING: *ELEMENT TYPE={etype} block had leftover "
                        f"tokens ({len(toks) - k}); check for a malformed record.\n")
                stats["converted"][etype] = stats["converted"].get(etype, 0) + cnt
            else:
                # unknown/already-linear: pass through, but record its nodes as
                # "used" so pruning never removes them. Assume col0=id, rest=nodes.
                if etype and etype not in FULL:
                    stats["passed"].add(etype)
                out.append(header)
                for dl in data:
                    out.append(dl)
                    if not dl.strip() or dl.strip().startswith("**"):
                        continue
                    parts = [t for t in dl.replace(",", " ").split() if t]
                    for nd in parts[1:]:
                        stats["elem_nodes"].add(nd)
            continue
        else:
            out.append(line); i += 1

    if not prune:
        return "\n".join(out) + "\n", stats

    used = stats["elem_nodes"]

    # ---- pass 2: prune *NODE not used by any element; filter NSET lists -----
    final, i, n = [], 0, len(out)
    while i < n:
        line = out[i]
        up = line.lstrip().upper()
        if _kw(line) and up.startswith("*NODE") and "OUTPUT" not in up \
                and "PRINT" not in up and "FILE" not in up:
            final.append(line); i += 1
            while i < n and not _kw(out[i]):
                dl = out[i]
                if not dl.strip() or dl.strip().startswith("**"):
                    final.append(dl); i += 1; continue
                nid = dl.split(",")[0].strip()
                if nid in used:
                    final.append(dl)
                else:
                    stats["orphans"] += 1
                i += 1
            continue
        if _kw(line) and up.startswith("*NSET"):
            final.append(line); i += 1
            while i < n and not _kw(out[i]):
                dl = out[i]
                if not dl.strip() or dl.strip().startswith("**"):
                    final.append(dl); i += 1; continue
                ids = [t.strip() for t in dl.split(",") if t.strip()]
                kept = [t for t in ids if (not t.lstrip("-").isdigit()) or t in used]
                if len(kept) != len(ids):
                    stats["nsets_filtered"] += 1
                if kept:
                    final.append(", ".join(kept) + ",")
                i += 1
            continue
        final.append(line); i += 1

    return "\n".join(final) + "\n", stats


def _selftest():
    # one C3D10 tet: corner nodes 1-4, midside 5-10; plus an NSET with a midside
    inp = """*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 0.0, 1.0, 0.0
4, 0.0, 0.0, 1.0
5, 0.5, 0.0, 0.0
6, 0.5, 0.5, 0.0
7, 0.0, 0.5, 0.0
8, 0.0, 0.0, 0.5
9, 0.5, 0.0, 0.5
10, 0.0, 0.5, 0.5
*ELEMENT, TYPE=C3D10, ELSET=RIVET
1, 1, 2, 3, 4, 5, 6,
7, 8, 9, 10
*NSET, NSET=GRIP
2, 3, 6, 7
"""
    txt, st = convert(inp, prune=True)
    assert "TYPE=C3D4" in txt, "type not downgraded"
    assert "1, 1, 2, 3, 4" in txt, "connectivity not truncated to corners"
    assert st["converted"].get("C3D10") == 1
    assert st["orphans"] == 6, f"expected 6 midside nodes pruned, got {st['orphans']}"
    # midside 6,7 should have been dropped from the NSET, leaving corners 2,3
    grip = txt.split("*NSET")[1]
    assert "6" not in grip.split("\n")[1] and "7" not in grip.split("\n")[1], \
        "midside nodes not filtered from NSET"
    print("selftest OK: C3D10 -> C3D4, 6 midside nodes pruned, NSET filtered to corners")
    print("---- converted deck ----")
    print(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp", nargs="?", help="input .inp")
    ap.add_argument("-o", "--out", help="output .inp (default: <in>_linear.inp)")
    ap.add_argument("--keep-nodes", action="store_true",
                    help="do NOT prune orphaned midside nodes")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    if not a.inp:
        ap.error("give an .inp file (or --selftest)")
    with open(a.inp, "r", errors="ignore") as fh:
        text = fh.read()
    out_text, st = convert(text, prune=not a.keep_nodes)
    out_path = a.out or re.sub(r"\.inp$", "", a.inp, flags=re.I) + "_linear.inp"
    with open(out_path, "w") as fh:
        fh.write(out_text)
    print(f"wrote {out_path}")
    if st["converted"]:
        for t, c in st["converted"].items():
            print(f"  {t:8s} -> {MAP[t][0]:8s}  {c} element(s)")
    else:
        print("  (no quadratic elements found - deck already linear?)")
    if st["orphans"]:
        print(f"  pruned {st['orphans']} orphaned midside node(s)")
    if st["nsets_filtered"]:
        print(f"  filtered midside nodes out of {st['nsets_filtered']} NSET line(s)")
    if st["passed"]:
        print(f"  WARNING: unrecognised element TYPE(s) passed through unchanged: "
              f"{', '.join(sorted(st['passed']))}")


if __name__ == "__main__":
    main()

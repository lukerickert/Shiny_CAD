# -*- coding: utf-8 -*-
"""Radioss cards of the constraints that inp2rad does not convert (kinematic and distributing couplings of reference
points, springs, joints and equations; constraints.py).

model_inp writes the cards into the .inp as comment lines "**RAD <card line>". The fields that need an identifier
hold a placeholder <Xn> (n: a number of the model) right-aligned in their field. After inp2rad, apply() takes the
lines into <stem>_0000.rad before /END and replaces each placeholder by a number above every identifier and node or
element number of the deck, right-aligned in the field width of the placeholder (the field with its leading blanks).

Cards:
  /GRNOD/NODE/<id>             node group (10 nodes per line)
  /RBE2/<id>                   main node, Trarot of the coupled components, node group
  /RBE3/<id>                   reference node, Trarot of the reference node, one node group per weight
  /PART, /PROP/TYPE13, /SPRING  springs (stiffnesses K1 to K6, the layout of the inp2rad TYPE13 springs)
  /MPC/<id>                    sum alpha * u = 0: one line per term: node, component 1 to 6, skew 0, alpha
  /ADMAS/5/<id>                added mass of single nodes (point and distributed masses): mass, node
  /TH/NODE/<id>                time history of nodes (history output): variables, one line per node with its name
  /TH/PART/<id>                time history of parts: variables, the part numbers; a part is given by its title as
                               <P:TITLE>, replaced by the number of the /PART with that title
  /TH/INTER/<id>               time history of interfaces: variables, interface numbers
  /GRBRIC/BRIC/<id>            solid element group (10 elements per line)
  /SECT/<id>                   section: three nodes of the section plane, the node group, the solid element group,
                               Iframe 11 (global system, geometric centre)
  /TH/SECTIO/<id>              time history of sections: variables, the sections
"""
import glob
import os
import re

PREFIX = "**RAD "


def trarot(flags):
    f = [1 if x else 0 for x in (list(flags) + [0] * 6)[:6]]
    return "   %d%d%d %d%d%d" % tuple(f)


class Cards(object):
    """Collects the card lines with placeholders."""

    def __init__(self):
        self.lines = []
        self.n = 0

    def ph(self, width=10):
        self.n += 1
        return ("<X%d>" % self.n).rjust(width), "<X%d>" % self.n

    def title(self, text):
        return (str(text) or "-")[:80]

    def grnod(self, title, nodes):
        f, tok = self.ph()
        self.lines += ["/GRNOD/NODE/%s" % tok, self.title(title)]
        nodes = sorted(int(n) for n in nodes)
        for k in range(0, len(nodes), 10):
            self.lines.append("".join("%10d" % n for n in nodes[k:k + 10]))
        return f

    def rbe2(self, title, main, nodes, flags):
        g = self.grnod(title + " nodes", nodes)
        f, tok = self.ph()
        self.lines += ["/RBE2/%s" % tok, self.title(title),
                       "#  node_IDm    Trarot   skew_ID   grnd_ID     Iflag",
                       "%10d%s%10d%s%10d" % (main, trarot(flags), 0, g, 0)]

    def rbe3(self, title, ref, weights, flags):
        """weights {node: weight}: one node group per weight value (4 significant digits)."""
        groups = {}
        for n, w in weights.items():
            groups.setdefault(float("%.4g" % w), []).append(n)
        gids = [(w, self.grnod("%s w %g" % (title, w), ns)) for w, ns in sorted(groups.items())]
        f, tok = self.ph()
        self.lines += ["/RBE3/%s" % tok, self.title(title),
                       "# Node_IDr Trarotref     N_set   I_modif",
                       "%10d%s%10d%10d" % (ref, trarot(flags), len(gids), 1),
                       "#                WTi Trarot_Mi  skew_Idi  grnd_IDi"]
        for w, g in gids:
            self.lines.append("%20.8g%s%10s%s" % (w, trarot([1, 1, 1, 0, 0, 0]), "", g))

    def spring(self, title, a, b, k, mass=1e-6, inertia=1e-6):
        """Spring element between nodes a and b with stiffnesses k[0..5] (/PROP/TYPE13)."""
        part, ptok = self.ph()
        self.lines += ["/PART/%s" % ptok, self.title(title), "#     prop       mat    subset", "%s         0         0" % part]
        self.lines += ["/PROP/TYPE13/%s" % ptok, self.title(title),
                       "#               Mass             Inertia   skew_ID   sens_ID    Isflag     Ifail     Ileng    Ifail2",
                       "%20.4e%20.4e         0         0         0         0         0         0" % (mass, inertia)]
        for i in range(6):
            self.lines += ["#                 K%d                  C%d                  A%d                  B%d                  D%d" % ((i + 1,) * 5),
                           "%20.6e                   0                   0                   0                   0" % float(k[i]),
                           "# fct_ID1%d        H%d  fct_ID2%d  fct_ID3%d  fct_ID4%d                    delta_min%d          delta_max%d" % ((i + 1,) * 7),
                           "         0         0         0         0         0                             0                   0",
                           "#                 F%d                  E%d             Ascale%d             Hscale%d" % ((i + 1,) * 4),
                           "                   0                   0                   0                   0"]
        self.lines += ["#                 V0              Omega0               F_cut   Fsmooth",
                       "                   0                   0                   0         0",
                       "#                  C                   n               alpha                beta"]
        self.lines += ["                   0                   0                   0                   0"] * 6
        e, _t = self.ph()
        self.lines += ["/SPRING/%s" % ptok, "#  Sprg_ID  NodeID_1  NodeID_2", "%s%10d%10d" % (e, a, b)]

    def mpc(self, title, terms):
        f, tok = self.ph()
        self.lines += ["/MPC/%s" % tok, self.title(title), "#  node_ID      ixyz   skew_ID               alpha"]
        for n, d, c in terms:
            self.lines.append("%10d%10d%10d%20.10g" % (n, d, 0, c))

    def admas(self, title, masses):
        """Added mass of single nodes (/ADMAS type 5): masses {node: mass t}, one line per node."""
        f, tok = self.ph()
        self.lines += ["/ADMAS/5/%s" % tok, self.title(title), "#               Mass   node_ID"]
        for n, m in sorted(masses.items()):
            if m > 0:
                self.lines.append("%20.8g%10d" % (m, n))

    def thnod(self, title, variables, nodes, prefix):
        """/TH/NODE: variables (10 per line), nodes with the names <prefix>N<node>."""
        f, tok = self.ph()
        self.lines += ["/TH/NODE/%s" % tok, self.title(title)]
        for k in range(0, len(variables), 10):
            self.lines.append("".join("%-10s" % v for v in variables[k:k + 10]))
        self.lines.append("#  node_ID   skew_ID node_name")
        for n in sorted(int(x) for x in nodes):
            self.lines.append("%10d%10d%sN%d" % (n, 0, prefix, n))

    def thpart(self, title, variables, part_titles):
        """/TH/PART: variables, the parts by title (<P:TITLE> resolved by apply())."""
        f, tok = self.ph()
        self.lines += ["/TH/PART/%s" % tok, self.title(title)]
        for k in range(0, len(variables), 10):
            self.lines.append("".join("%-10s" % v for v in variables[k:k + 10]))
        toks = ["<P:%s>" % t for t in part_titles]
        for k in range(0, len(toks), 10):
            self.lines.append("".join(t.rjust(10) if len(t) < 10 else " " + t for t in toks[k:k + 10]))

    def thinter(self, title, variables, inter_ids):
        """/TH/INTER of interfaces given by their numbers."""
        f, tok = self.ph()
        self.lines += ["/TH/INTER/%s" % tok, self.title(title), "".join("%-10s" % v for v in variables[:10])]
        self.lines += ["".join("%10d" % int(i) for i in inter_ids[k:k + 10]) for k in range(0, len(inter_ids), 10)]

    def grbric(self, title, elems):
        f, tok = self.ph()
        self.lines += ["/GRBRIC/BRIC/%s" % tok, self.title(title)]
        elems = sorted(int(e) for e in elems)
        for k in range(0, len(elems), 10):
            self.lines.append("".join("%10d" % e for e in elems[k:k + 10]))
        return f

    def sect(self, title, n3, nodes, elems):
        """/SECT of the nodes and the solid elements on one side of a section; n3: three nodes of the plane. Returns
        the field of its number."""
        g = self.grnod(title + " nodes", nodes)
        b = self.grbric(title + " elements", elems)
        f, tok = self.ph()
        self.lines += ["/SECT/%s" % tok, self.title(title),
                       "# node_ID1  node_ID2  node_ID3   grnd_ID     ISAVE  frame_ID",
                       "%10d%10d%10d%s%10d%10d" % (n3[0], n3[1], n3[2], g, 0, 0), "SECT",
                       "# grbric_ID          grshel_ID grtrus_ID grbeam_ID grsprg_ID grtria_ID    Ninter              Iframe",
                       "%s%10d%10d%10d%10d%10d%10d%10d%10d%10d" % (b, 0, 0, 0, 0, 0, 0, 0, 0, 11)]
        return f

    def thsect(self, title, variables, sect_fields):
        f, tok = self.ph()
        self.lines += ["/TH/SECTIO/%s" % tok, self.title(title), "".join("%-10s" % v for v in variables[:10]),
                       "".join(sect_fields)]

    def inp_lines(self):
        return [PREFIX + ln for ln in self.lines]


_TOKEN = re.compile(r" *<X(\d+)>")
_PART = re.compile(r" *<P:([^>]*)>")


def part_ids(rad_text):
    """{title (upper case): /PART number} of a deck."""
    out = {}
    L = rad_text.splitlines()
    for i, ln in enumerate(L):
        m = re.match(r"/PART/(\d+)\s*$", ln.strip())
        if m and i + 1 < len(L):
            out.setdefault(L[i + 1].strip().upper(), int(m.group(1)))
    return out


def _max_id(rad_text):
    m = 0
    for ln in rad_text.splitlines():
        if ln.startswith("#") or not ln.strip():
            continue
        if ln.startswith("/"):
            for v in re.findall(r"/(\d+)", ln):
                m = max(m, int(v))
            continue
        v = ln[:10].strip()
        if v.isdigit():
            m = max(m, int(v))
    return m


def apply(inp_path, rad_path=None):
    """Writes the **RAD cards of inp_path into its _0000.rad (default: <stem>_0000.rad next to the .inp, else the
    newest *_0000.rad there). Returns the number of card lines written (0: none)."""
    with open(inp_path, "r", errors="replace") as f:
        lines = [ln.rstrip("\n")[len(PREFIX):] for ln in f if ln.startswith(PREFIX)]
    if not lines:
        return 0
    if rad_path is None:
        stem = os.path.splitext(inp_path)[0]
        rad_path = stem + "_0000.rad"
        if not os.path.isfile(rad_path):
            c = sorted(glob.glob(os.path.join(os.path.dirname(inp_path) or ".", "*_0000.rad")) + glob.glob("*_0000.rad"),
                       key=os.path.getmtime)
            if not c:
                raise FileNotFoundError("no _0000.rad next to %s" % inp_path)
            rad_path = c[-1]
    with open(rad_path, "r", errors="replace") as f:
        text = f.read()
    if "# SHINYCAD constraints" in text:
        return 0
    base = (_max_id(text) // 1000 + 1) * 1000
    out = ["#---1----|----2----|----3----|----4----|----5----|----6----|----7----|----8----|----9----|---10----|",
           "# SHINYCAD constraints (couplings, springs, joints, equations) and time history",
           "#---1----|----2----|----3----|----4----|----5----|----6----|----7----|----8----|----9----|---10----|"]
    pids = part_ids(text) if any("<P:" in ln for ln in lines) else {}

    def part(m):
        t = m.group(1).strip().upper()
        if t not in pids:
            raise ValueError("time history: no /PART with the title %s in %s" % (t, os.path.basename(rad_path)))
        return "%10d" % pids[t]
    for ln in lines:
        ln = _PART.sub(part, ln)
        out.append(_TOKEN.sub(lambda m: str(base + int(m.group(1))).rjust(len(m.group(0))) if len(m.group(0)) > len("<X%s>" % m.group(1))
                              else str(base + int(m.group(1))), ln))
    k = text.rfind("\n/END")
    if k < 0:
        text = text.rstrip("\n") + "\n" + "\n".join(out) + "\n/END\n"
    else:
        text = text[:k + 1] + "\n".join(out) + "\n" + text[k + 1:]
    with open(rad_path, "w") as f:
        f.write(text)
    return len(out)

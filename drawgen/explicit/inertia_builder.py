#!/usr/bin/env python3
"""
inertia_builder.py — GUI front end for inertia_calc.py.

Build up an impactor from uniform box primitives the way you'd sketch it:
a table of parts (name, mass, CG position, dimensions), a live scaled
side-view of the rectangles with per-part CG dots and the assembly CG,
and live mass properties (total mass, CG, inertia tensor about CG,
radii of gyration).

JSON save/load uses the same schema as inertia_calc.py, so files move
freely between the GUI and the command-line tool.

Requires: Python 3 with tkinter (standard on Windows). Computation is
imported from inertia_calc.py, which must sit in the same folder — the
math lives in exactly one place.
"""

import json
import math
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from inertia_calc import (compute, principal, rotation_matrix,
                              rotate_tensor, principal_misalignment,
                              axis_L_tilt, emit_rbody)
except ImportError:
    sys.exit("ERROR: inertia_calc.py not found next to inertia_builder.py. "
             "Fix: keep both files in the same folder.")

FIELDS = ("name", "mass", "cx", "cy", "cz", "Lx", "Ly", "Lz")
NUMERIC = FIELDS[1:]


class Builder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Inertia builder — box primitives")
        # Same icon as the workspace (workspace_icon.ico/.png next to the
        # scripts, from LOGO.svg). Optional and non-fatal - standalone use
        # away from the workspace folder just keeps the stock Tk icon.
        _here = os.path.dirname(os.path.abspath(__file__))
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "SHINYCAD.inertia_builder")
            except Exception:
                pass
            _ico = os.path.join(_here, "workspace_icon.ico")
            if os.path.isfile(_ico):
                try:
                    self.iconbitmap(default=_ico)
                except tk.TclError:
                    pass
        _png = os.path.join(_here, "workspace_icon.png")
        if os.path.isfile(_png):
            try:
                self._app_icon_img = tk.PhotoImage(file=_png)
                self.iconphoto(True, self._app_icon_img)
            except tk.TclError:
                pass
        self.geometry("1180x640")
        self.prims = []          # list of dicts in inertia_calc schema
        self.current_path = None
        self._build_ui()
        self._refresh()

    # ---------------- UI construction ----------------
    def _build_ui(self):
        root = ttk.Frame(self, padding=6)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # Left: table + entry form + buttons
        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 6))

        cols = FIELDS
        self.tree = ttk.Treeview(left, columns=cols, show="headings",
                                 height=12, selectmode="browse")
        widths = (90, 60, 60, 60, 60, 60, 60, 60)
        for c, w in zip(cols, widths):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="e" if c != "name" else "w")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        form = ttk.Frame(left)
        form.pack(fill="x", pady=(8, 4))
        self.vars = {}
        for i, f in enumerate(FIELDS):
            ttk.Label(form, text=f).grid(row=0, column=i, padx=2)
            v = tk.StringVar()
            e = ttk.Entry(form, textvariable=v, width=9 if f == "name" else 7)
            e.grid(row=1, column=i, padx=2)
            self.vars[f] = v
            e.bind("<Return>", lambda _e: self._add_or_update())

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=4)
        for txt, cmd in (("Add / update", self._add_or_update),
                         ("Delete", self._delete),
                         ("Duplicate", self._duplicate),
                         ("Clear form", self._clear_form)):
            ttk.Button(btns, text=txt, command=cmd).pack(side="left", padx=2)

        io = ttk.Frame(left)
        io.pack(fill="x", pady=4)
        for txt, cmd in (("Open JSON…", self._open),
                         ("Save", self._save),
                         ("Save as…", self._save_as),
                         ("Copy inertia payload", self._copy_payload),
                         ("Export /RBODY…", self._export_rbody)):
            ttk.Button(io, text=txt, command=cmd).pack(side="left", padx=2)

        self.units_var = tk.StringVar(value="mm, t")
        uf = ttk.Frame(left)
        uf.pack(fill="x", pady=(4, 8))
        ttk.Label(uf, text="units label:").pack(side="left")
        ttk.Entry(uf, textvariable=self.units_var, width=24).pack(side="left", padx=4)

        tf = ttk.Frame(left)
        tf.pack(fill="x", pady=(0, 8))
        ttk.Label(tf, text="tilt about CG:").pack(side="left")
        self.tilt_axis_var = tk.StringVar(value="Z")
        ttk.Combobox(tf, textvariable=self.tilt_axis_var, width=3,
                     state="readonly", values=("X", "Y", "Z")
                     ).pack(side="left", padx=4)
        self.tilt_deg_var = tk.StringVar(value="0")
        te = ttk.Entry(tf, textvariable=self.tilt_deg_var, width=7)
        te.pack(side="left")
        ttk.Label(tf, text="deg").pack(side="left", padx=(2, 0))
        te.bind("<Return>", lambda _e: self._refresh())
        ttk.Button(tf, text="Apply", command=self._refresh
                   ).pack(side="left", padx=6)
        self.tilt_axis_var.trace_add("write", lambda *_: self._refresh())

        self.results = tk.Text(left, width=58, height=18, font=("Consolas", 9),
                               state="disabled", relief="flat")
        self.results.pack(fill="both", expand=True)

        # Right: canvas preview
        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        bar = ttk.Frame(right)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="View plane:").pack(side="left")
        self.plane_var = tk.StringVar(value="XY")
        for p in ("XY", "XZ", "YZ"):
            ttk.Radiobutton(bar, text=p, value=p, variable=self.plane_var,
                            command=self._draw).pack(side="left", padx=2)
        self.canvas = tk.Canvas(right, background="white",
                                highlightthickness=1,
                                highlightbackground="#999")
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _e: self._draw())

    # ---------------- table / form actions ----------------
    def _read_form(self):
        name = self.vars["name"].get().strip()
        if not name:
            raise ValueError("name is empty. Fix: give the part a name.")
        vals = {}
        for f in NUMERIC:
            raw = self.vars[f].get().strip().replace(",", ".")
            if raw == "":
                raise ValueError(f"'{f}' is empty. Fix: enter a number "
                                 f"(0 is allowed for dims).")
            try:
                vals[f] = float(raw)
            except ValueError:
                raise ValueError(f"'{f}' = {raw!r} is not a number.")
        if vals["mass"] <= 0:
            raise ValueError("mass must be > 0.")
        if any(vals[d] < 0 for d in ("Lx", "Ly", "Lz")):
            raise ValueError("dims must be >= 0 (0 = point/plate/rod).")
        return {"name": name, "mass": vals["mass"],
                "center": [vals["cx"], vals["cy"], vals["cz"]],
                "dims": [vals["Lx"], vals["Ly"], vals["Lz"]]}

    def _add_or_update(self):
        try:
            prim = self._read_form()
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))
            return
        names = [p["name"] for p in self.prims]
        if prim["name"] in names:
            self.prims[names.index(prim["name"])] = prim
        else:
            self.prims.append(prim)
        self._refresh()

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.tree.item(sel[0], "values")[0]
        self.prims = [p for p in self.prims if p["name"] != name]
        self._refresh()

    def _duplicate(self):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.tree.item(sel[0], "values")[0]
        src = next(p for p in self.prims if p["name"] == name)
        copy = json.loads(json.dumps(src))
        base = copy["name"]
        n = 2
        names = {p["name"] for p in self.prims}
        while f"{base}_{n}" in names:
            n += 1
        copy["name"] = f"{base}_{n}"
        self.prims.append(copy)
        self._refresh()

    def _clear_form(self):
        for v in self.vars.values():
            v.set("")

    def _on_select(self, _e):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        for f, v in zip(FIELDS, vals):
            self.vars[f].set(v)

    # ---------------- file I/O ----------------
    def _open(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            prims = data["primitives"]
        except Exception as e:
            messagebox.showerror("Load failed", f"{e}")
            return
        self.prims = prims
        self.units_var.set(data.get("units", "unspecified"))
        t = data.get("tilt")
        if isinstance(t, dict) and "axis" in t and "deg" in t:
            self.tilt_axis_var.set(str(t["axis"]).upper())
            self.tilt_deg_var.set(str(t["deg"]))
        else:
            self.tilt_deg_var.set("0")
        self.current_path = path
        self._refresh()

    def _save(self):
        if not self.current_path:
            return self._save_as()
        self._write(self.current_path)

    def _save_as(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        self.current_path = path
        self._write(path)

    def _write(self, path):
        data = {"units": self.units_var.get(), "primitives": self.prims}
        axis, deg = self._read_tilt()
        if deg != 0.0:
            data["tilt"] = {"axis": axis, "deg": deg}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.title(f"Inertia builder — {os.path.basename(path)}")

    def _read_tilt(self):
        """Return (axis, deg) or (axis, 0.0). Invalid entry -> error box."""
        axis = self.tilt_axis_var.get()
        raw = self.tilt_deg_var.get().strip().replace(",", ".")
        if raw == "":
            return axis, 0.0
        try:
            return axis, float(raw)
        except ValueError:
            messagebox.showerror("Invalid input",
                                 f"tilt angle {raw!r} is not a number.")
            self.tilt_deg_var.set("0")
            return axis, 0.0

    def _payload_and_block(self):
        """Compute the /RBODY payload dict and formatted block for the current
        model, honouring the tilt field. Returns (comps, block) or (None, None)
        with a message if there are no primitives."""
        if not self.prims:
            messagebox.showinfo("No model", "Add at least one primitive first.")
            return None, None
        M, cg, I, _ = compute(self.prims)
        axis, deg = self._read_tilt()
        tilt = {"axis": axis, "deg": deg} if deg != 0.0 else None
        comps, block = emit_rbody(M, cg, I, tilt=tilt)
        return comps, block

    def _copy_payload(self):
        """Put the flat JSON payload (mass, cx..cz, Jxx..Jxz) on the clipboard —
        the exact keys the workspace 'Inertia' tab reads."""
        comps, _ = self._payload_and_block()
        if comps is None:
            return
        self.clipboard_clear()
        self.clipboard_append(json.dumps(comps, indent=2))
        messagebox.showinfo("Copied",
                            "Inertia payload copied to clipboard.\n\n"
                            "Paste into a .json file and point the workspace "
                            "'1b. Inertia' tab at it.")

    def _export_rbody(self):
        """Write the payload to a .json (for the workspace tab) and the human-
        readable /RBODY block to a sibling .txt for reference."""
        comps, block = self._payload_and_block()
        if comps is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            title="Export inertia payload (JSON the workspace tab reads)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(comps, f, indent=2)
            txt = os.path.splitext(path)[0] + "_RBODY.txt"
            with open(txt, "w", encoding="utf-8") as f:
                f.write(block + "\n")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
            return
        messagebox.showinfo("Exported",
                            f"Wrote:\n  {os.path.basename(path)}  (point the workspace at this)\n"
                            f"  {os.path.basename(txt)}  (/RBODY block for reference)")

    # ---------------- refresh: table, results, canvas ----------------
    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for p in self.prims:
            row = (p["name"], p["mass"], *p["center"], *p["dims"])
            self.tree.insert("", "end", values=row)
        self._update_results()
        self._draw()

    def _update_results(self):
        self.results.configure(state="normal")
        self.results.delete("1.0", "end")
        if not self.prims:
            self.results.insert("end", "No primitives yet.\n")
            self.results.configure(state="disabled")
            return
        M, cg, I, rows = compute(self.prims)
        ev = principal(I)
        lines = []
        lines.append(f"Total mass : {M:.6g}")
        lines.append(f"CG         : [{cg[0]:.6g}, {cg[1]:.6g}, {cg[2]:.6g}]")
        lines.append("")
        lines.append("Inertia tensor about CG:")
        lab = ("x", "y", "z")
        lines.append("     " + "".join(f"{l:>12}" for l in lab))
        for a in range(3):
            lines.append(f"  {lab[a]}  " +
                         "".join(f"{I[a][b]:>12.5g}" for b in range(3)))
        off = max(abs(I[0][1]), abs(I[0][2]), abs(I[1][2]))
        diag = max(abs(I[k][k]) for k in range(3))
        lines.append("")
        lines.append(f"Max product : {off:.5g} ({100*off/diag:.1f}% of diag)")
        if diag > 0 and off / diag > 0.05:
            lines.append("NOTE: products exceed 5% — enter the full tensor")
            lines.append("      or align model axes with principal axes.")
        lines.append("Principal I : " + ", ".join(f"{v:.5g}" for v in ev))
        lines.append("k           : " +
                     ", ".join(f"{math.sqrt(v / M):.5g}" for v in ev))
        mis = principal_misalignment(I)
        tl = axis_L_tilt(I)
        lines.append(f"axes vs principal: {mis:.2f} deg  (0 = principal)")
        lines.append(f"spin-L tilt x/y/z: "
                     f"{tl[0]:.2f} / {tl[1]:.2f} / {tl[2]:.2f} deg")
        axis, deg = self._read_tilt()
        if deg != 0.0:
            R = rotation_matrix(axis, deg)
            Ig = rotate_tensor(I, R)
            lines.append("")
            lines.append(f"Tilted {deg:g} deg about {axis} (about CG):")
            lines.append("     " + "".join(f"{l:>12}" for l in lab))
            for a in range(3):
                lines.append(f"  {lab[a]}  " +
                             "".join(f"{Ig[a][b]:>12.5g}" for b in range(3)))
            offg = max(abs(Ig[0][1]), abs(Ig[0][2]), abs(Ig[1][2]))
            diagg = max(abs(Ig[k][k]) for k in range(3))
            lines.append(f"Max product : {offg:.5g} "
                         f"({100*offg/diagg:.1f}% of diag)")
            if diagg > 0 and offg / diagg > 0.05:
                lines.append("NOTE: enter all six components; diagonal-only")
                lines.append("      entry drops the products.")
        self.results.insert("end", "\n".join(lines))
        self.results.configure(state="disabled")

    # ---------------- canvas ----------------
    def _draw(self):
        cv = self.canvas
        cv.delete("all")
        if not self.prims:
            return
        plane = self.plane_var.get()
        ax = {"XY": (0, 1), "XZ": (0, 2), "YZ": (1, 2)}[plane]

        axis, deg = self._read_tilt()
        M, cg, _, _ = compute(self.prims)
        R = rotation_matrix(axis, deg) if deg != 0.0 else None

        def xform(pt):
            """Rotate a world point about the assembly CG (if tilted)."""
            if R is None:
                return pt
            d = [pt[k] - cg[k] for k in range(3)]
            return [cg[a] + sum(R[a][k] * d[k] for k in range(3))
                    for a in range(3)]

        def corners(p):
            cx, cy, cz = p["center"]
            hx, hy, hz = (p["dims"][0] / 2, p["dims"][1] / 2,
                          p["dims"][2] / 2)
            return [xform([cx + sx * hx, cy + sy * hy, cz + sz * hz])
                    for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]

        def hull(pts2):
            """Convex hull (monotone chain) of 2D points."""
            pts = sorted(set(pts2))
            if len(pts) <= 2:
                return pts
            def cross(o, a, b):
                return ((a[0] - o[0]) * (b[1] - o[1])
                        - (a[1] - o[1]) * (b[0] - o[0]))
            lower, upper = [], []
            for p in pts:
                while len(lower) > 1 and cross(lower[-2], lower[-1], p) <= 0:
                    lower.pop()
                lower.append(p)
            for p in reversed(pts):
                while len(upper) > 1 and cross(upper[-2], upper[-1], p) <= 0:
                    upper.pop()
                upper.append(p)
            return lower[:-1] + upper[:-1]

        # world extents from (possibly rotated) corners
        all_pts = [c for p in self.prims for c in corners(p)]
        lo = [min(pt[ax[k]] for pt in all_pts) for k in range(2)]
        hi = [max(pt[ax[k]] for pt in all_pts) for k in range(2)]
        span = [max(hi[k] - lo[k], 1e-9) for k in range(2)]
        W = max(cv.winfo_width(), 50)
        H = max(cv.winfo_height(), 50)
        margin = 50
        scale = min((W - 2 * margin) / span[0], (H - 2 * margin) / span[1])

        def to_px(u, v):
            x = margin + (u - lo[0]) * scale
            y = H - margin - (v - lo[1]) * scale   # flip: world up = screen up
            return x, y

        # axes labels
        cv.create_text(W - 16, H - 12, text=plane[0], font=("Consolas", 10))
        cv.create_text(14, 16, text=plane[1], font=("Consolas", 10))
        if R is not None:
            cv.create_text(margin, H - 12, anchor="w", font=("Consolas", 9),
                           text=f"tilted {deg:g} deg about {axis} (about CG)")

        colors = ("#4477aa", "#ee6677", "#228833", "#ccbb44",
                  "#66ccee", "#aa3377", "#bbbbbb")
        for i, p in enumerate(self.prims):
            col = colors[i % len(colors)]
            pts2 = [(c[ax[0]], c[ax[1]]) for c in corners(p)]
            h = hull(pts2)
            cc = xform(p["center"])
            x, y = to_px(cc[ax[0]], cc[ax[1]])
            if len(h) <= 2:
                cv.create_oval(x - 5, y - 5, x + 5, y + 5,
                               outline=col, width=2)
            else:
                flat = [v for u, vv in h for v in to_px(u, vv)]
                cv.create_polygon(*flat, outline=col, width=2, fill="")
            cv.create_oval(x - 2, y - 2, x + 2, y + 2, fill=col, outline=col)
            cv.create_text(x, y - 12, text=f'{p["name"]} ({p["mass"]:g})',
                           fill=col, font=("Consolas", 9))

        # assembly CG crosshair
        x, y = to_px(cg[ax[0]], cg[ax[1]])
        r = 8
        cv.create_line(x - r, y, x + r, y, width=2)
        cv.create_line(x, y - r, x, y + r, width=2)
        cv.create_oval(x - r, y - r, x + r, y + r, width=2)
        cv.create_text(x + 12, y + 12, anchor="nw", font=("Consolas", 9),
                       text=f"CG [{cg[ax[0]]:.4g}, {cg[ax[1]]:.4g}]  M={M:g}")


if __name__ == "__main__":
    Builder().mainloop()

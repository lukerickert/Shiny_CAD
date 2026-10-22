# -*- coding: utf-8 -*-
"""ISO 5457 frame and ISO 7200 title block as sheet primitives.

Sheet primitives use sheet coordinates (mm, origin bottom-left, y up):
    ("line", x1, y1, x2, y2, layer)
    ("circle", cx, cy, r, layer)
    ("arc", cx, cy, r, a0, a1, layer)          counter-clockwise, degrees
    ("poly", [(x, y), ...], layer, closed)
    ("solid", [(x, y), ...], layer)            filled polygon
    ("text", x, y, height, text, layer, anchor[, key]) anchor: start | middle | end;
                                               key: title block field name
    ("image", x, y, w, h, path)
"""
import os


def sheet_size(cfg, sheet):
    w, h = cfg["sheet_sizes_mm"][sheet]
    return float(w), float(h)


def frame_rect(cfg, sheet):
    """Inner frame (x0, y0, x1, y1), sheet coordinates."""
    w, h = sheet_size(cfg, sheet)
    b = cfg["border"]
    return b["left_mm"], b["other_mm"], w - b["other_mm"], h - b["other_mm"]


def title_block_rect(cfg, sheet):
    """Title block (x0, y0, x1, y1), sheet coordinates."""
    _, y0, x1, _ = frame_rect(cfg, sheet)
    tb = cfg["title_block"]
    return x1 - tb["width_mm"], y0, x1, y0 + tb["height_mm"]


def _rect(x, y, w, h, layer):
    return [("line", x, y, x + w, y, layer), ("line", x + w, y, x + w, y + h, layer),
            ("line", x + w, y + h, x, y + h, layer), ("line", x, y + h, x, y, layer)]


def projection_symbol(x, y, w, h, first_angle=True, layer="title"):
    """ISO 5456-2 projection symbol centred in the cell (x, y lower-left)."""
    d = min(h * 0.55, w * 0.22)
    d2 = d * 0.5
    L = d * 1.2
    gap = d * 0.6
    total = L + gap + d
    x0 = x + (w - total) / 2.0
    cy = y + h / 2.0 - 1.0
    if first_angle:
        tx, ccx = x0, x0 + L + gap + d / 2.0
    else:
        ccx, tx = x0 + d / 2.0, x0 + d + gap
    ext = 1.5
    pts = [(tx, cy - d2 / 2), (tx + L, cy - d / 2), (tx + L, cy + d / 2), (tx, cy + d2 / 2)]
    return [
        ("poly", pts, layer, True),
        ("circle", ccx, cy, d / 2, layer),
        ("circle", ccx, cy, d2 / 2, layer),
        ("line", tx - ext, cy, tx + L + ext, cy, "chain"),
        ("line", ccx - d / 2 - ext, cy, ccx + d / 2 + ext, cy, "chain"),
        ("line", ccx, cy - d / 2 - ext, ccx, cy + d / 2 + ext, "chain"),
    ]


def sheet_primitives(cfg, sheet, values, first_angle=True, base_dir=""):
    """Frame, centring marks and title block with field values."""
    W, H = sheet_size(cfg, sheet)
    x0, y0, x1, y1 = frame_rect(cfg, sheet)
    tb = cfg["title_block"]
    p = _rect(x0, y0, x1 - x0, y1 - y0, "frame")
    if cfg["border"].get("centring_marks", True):
        p += [("line", W / 2, H, W / 2, y1 - 5, "frame"), ("line", W / 2, 0, W / 2, y0 + 5, "frame"),
              ("line", 0, H / 2, x0 + 5, H / 2, "frame"), ("line", W, H / 2, x1 - 5, H / 2, "frame")]
    tx, ty0, tx1, ty1 = title_block_rect(cfg, sheet)
    p += _rect(tx, ty0, tx1 - tx, ty1 - ty0, "frame")

    def cell_rect(cx, cy, cw, ch):
        # cell coordinates are measured from the top-left corner of the title block
        return tx + cx, ty1 - cy - ch, cw, ch

    for cell in (tb["logo_cell"], tb["projection_cell"]):
        p += _rect(*cell_rect(*cell), layer="title")
    px, py, pw, ph = cell_rect(*tb["projection_cell"])
    p += projection_symbol(px, py, pw, ph, first_angle)

    logo = tb.get("logo_file", "")
    if logo:
        path = logo if os.path.isabs(logo) else os.path.join(base_dir, logo)
        if os.path.isfile(path):
            lx, ly, lw, lh = cell_rect(*tb["logo_cell"])
            p.append(("image", lx + 1, ly + 1, lw - 2, lh - 2, path))

    ls = float(tb["label_size_mm"])
    for c in tb["cells"]:
        cx, cy, cw, ch = cell_rect(c["x"], c["y"], c["w"], c["h"])
        p += _rect(cx, cy, cw, ch, "title")
        p.append(("text", cx + 1.0, cy + ch - ls - 0.8, ls, c["label"], "text", "start"))
        size = float(c.get("size", 2.5))
        val = str(values.get(c["key"], ""))
        room = ch - ls - 0.8
        vy = cy + max((room - size) / 2.0, 0.8)
        p.append(("text", cx + 1.5, vy, size, val, "text", "start", c["key"]))
    return p


def drawing_area(cfg, sheet, margin=5.0, extra_bottom=0.0):
    """Area for views (x0, y0, x1, y1): inside the frame and above the title block (and the parts list)."""
    x0, y0, x1, y1 = frame_rect(cfg, sheet)
    return x0 + margin, y0 + cfg["title_block"]["height_mm"] + extra_bottom + margin, x1 - margin, y1 - margin


# --------------------------------------------------------------------------- parts list

PL_COLS = [("Item", 12.0, "middle"), ("Qty", 12.0, "middle"), ("Name", 0.0, "start"), ("Material", 40.0, "start"), ("Mass", 26.0, "end")]
PL_ROW = 7.0


def parts_list_height(rows):
    return (len(rows) + 1) * PL_ROW if rows else 0.0


def parts_list_primitives(cfg, sheet, rows):
    """Parts list table above the title block (same width), one row per item; header at the bottom (ISO 7573)."""
    if not rows:
        return []
    tx, ty0, tx1, ty1 = title_block_rect(cfg, sheet)
    width = tx1 - tx
    fixed = sum(w for _, w, _ in PL_COLS if w > 0)
    cols = [(n, w if w > 0 else width - fixed, a) for n, w, a in PL_COLS]
    p = []
    y = ty1
    h = PL_ROW
    hs = float(cfg["title_block"].get("label_size_mm", 1.8))
    th = 3.0
    # header row directly above the title block, items above it in reverse order (item 1 lowest)
    all_rows = [("Item", "Qty", "Name", "Material", "Mass")] + [(str(r.get("item", "")), str(r.get("qty", "")), str(r.get("name", "")),
                                                                 str(r.get("material", "")), str(r.get("mass", ""))) for r in rows]
    for i, vals in enumerate(all_rows):
        p += _rect(tx, y, width, h, "title")
        x = tx
        for (name, w, anchor), v in zip(cols, vals):
            if x > tx:
                p.append(("line", x, y, x, y + h, "title"))
            size = hs if i == 0 else th
            if anchor == "middle":
                p.append(("text", x + w / 2.0, y + (h - size) / 2.0, size, v, "text", "middle"))
            elif anchor == "end":
                p.append(("text", x + w - 1.5, y + (h - size) / 2.0, size, v, "text", "end"))
            else:
                p.append(("text", x + 1.5, y + (h - size) / 2.0, size, v, "text", "start"))
            x += w
        y += h
    return p

# -*- coding: utf-8 -*-
"""SVG, PDF (reportlab) and DXF (ezdxf) output of a composed drawing.

Primitive types: line, circle, arc, poly, solid, text, rtext (rotated text),
image, and group ("group", id, [primitives]) for annotations.
"""
import base64
import io
import math
import os
from xml.sax.saxutils import escape, quoteattr

CAP_TO_EM = 1.0 / 0.72          # font size from capital height (Helvetica / Arial)

# ISO 128 line types (mm)
DASH = {
    "hidden": [3.0, 0.75],
    "chain": [6.0, 0.75, 0.15, 0.75],
}


def _layers(cfg):
    lw = cfg["line_widths_mm"]
    return {
        "visible": {"w": lw["visible"], "dash": None},
        "hidden": {"w": lw["hidden"], "dash": DASH["hidden"]},
        "chain": {"w": lw["chain"], "dash": DASH["chain"]},
        "hatch": {"w": lw["hatch"], "dash": None},
        "dim": {"w": lw.get("dim", 0.25), "dash": None},
        "text": {"w": lw["text"], "dash": None},
        "frame": {"w": lw["frame"], "dash": None},
        "title": {"w": lw["title"], "dash": None},
    }


def style_of(L, name):
    """Style for a layer name; "lw:<width>:<continuous|hidden|chain|dot>" gives an explicit width."""
    if isinstance(name, str) and name.startswith("lw:"):
        try:
            _, w, cls = name.split(":")
            w = float(w)
        except ValueError:
            return L["visible"]
        dash = {"hidden": DASH["hidden"], "chain": DASH["chain"], "dot": [0.0, 1.0]}.get(cls)
        return {"w": w, "dash": dash}
    return L.get(name, L["visible"])


def _text_args(p):
    """(x, y, h, text, anchor, angle) for text and rtext primitives."""
    if p[0] == "text":
        return p[1], p[2], p[3], p[4], p[6], 0.0
    return p[1], p[2], p[3], p[4], p[5], p[6]


def flatten(prims):
    for p in prims:
        if p[0] == "group":
            for q in p[2]:
                yield q
        else:
            yield p


# --------------------------------------------------------------------------- SVG

def _svg_el(p, H, L, inline):
    """SVG element for one primitive. inline: stroke attributes on the element."""
    k = p[0]

    def Y(y):
        return H - y

    def st(layer):
        if not inline:
            return ""
        s = style_of(L, layer)
        a = ' fill="none" stroke="#000" stroke-width="%.3f"' % s["w"]
        if s["dash"]:
            a += ' stroke-dasharray="%s"' % ",".join("%.3f" % v for v in s["dash"])
        return a

    if k == "line":
        return '<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f"%s/>' % (p[1], Y(p[2]), p[3], Y(p[4]), st(p[5]))
    if k == "circle":
        return '<circle cx="%.3f" cy="%.3f" r="%.3f"%s/>' % (p[1], Y(p[2]), p[3], st(p[4]))
    if k == "arc":
        cx, cy, r, a0, a1, layer = p[1:]
        x0, y0 = cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))
        x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
        span = (a1 - a0) % 360.0
        return ('<path d="M %.3f %.3f A %.3f %.3f 0 %d 0 %.3f %.3f"%s/>'
                % (x0, Y(y0), r, r, 1 if span > 180 else 0, x1, Y(y1), st(layer)))
    if k == "poly":
        pts = " ".join("%.3f,%.3f" % (x, Y(y)) for x, y in p[1])
        return '<%s points="%s"%s/>' % ("polygon" if p[3] else "polyline", pts, st(p[2]))
    if k == "solid":
        pts = " ".join("%.3f,%.3f" % (x, Y(y)) for x, y in p[1])
        return '<polygon points="%s" fill="#000" stroke="none"/>' % pts
    if k in ("text", "rtext"):
        x, y, h, t, anchor, ang = _text_args(p)
        if not t:
            return ""
        rot = ' transform="rotate(%.3f %.3f %.3f)"' % (-ang, x, Y(y)) if abs(ang) > 1e-9 else ""
        return ('<text x="%.3f" y="%.3f" font-size="%.3f" text-anchor="%s"%s>%s</text>'
                % (x, Y(y), h * CAP_TO_EM, anchor, rot, escape(t)))
    return ""


def to_svg(d, cfg):
    W, H = d["size"]
    L = _layers(cfg)
    font = escape(cfg["title_block"].get("font", "sans-serif"))
    out = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'width="%gmm" height="%gmm" viewBox="0 0 %g %g">' % (W, H, W, H),
           '<rect x="0" y="0" width="%g" height="%g" fill="#fff"/>' % (W, H)]
    groups, texts, images, anns = {}, [], [], []
    for p in d["prims"]:
        k = p[0]
        if k in ("line", "circle", "arc", "poly"):
            layer = {"line": 5, "circle": 4, "arc": 6, "poly": 2}[k]
            groups.setdefault(p[layer], []).append(_svg_el(p, H, L, False))
        elif k in ("solid", "text", "rtext"):
            texts.append(_svg_el(p, H, L, False))
        elif k == "image":
            x, y, w, h, path = p[1:]
            images.append(_svg_image(x, H - (y + h), w, h, path))
        elif k == "group":
            items = [_svg_el(q, H, L, True) for q in p[2]]
            hit = ['<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" stroke="transparent" stroke-width="2.5"/>'
                   % (q[1], H - q[2], q[3], H - q[4]) for q in p[2] if q[0] == "line"]
            anns.append('<g class="ann" data-ann=%s font-family="%s">%s%s</g>'
                        % (quoteattr(str(p[1])), font, "".join(hit), "".join(items)))
    for name, items in groups.items():
        st = style_of(L, name)
        dash = ""
        if st["dash"]:
            dash = ' stroke-dasharray="%s"' % ",".join("%.3f" % v for v in st["dash"])
        out.append('<g fill="none" stroke="#000" stroke-width="%.3f" stroke-linecap="round"%s>'
                   % (st["w"], dash))
        out += items
        out.append("</g>")
    out.append('<g font-family="%s" fill="#000">' % font)
    out += texts
    out.append("</g>")
    out += images
    out += anns
    out.append("</svg>")
    return "\n".join(out)


def _svg_image(x, y, w, h, path):
    ext = os.path.splitext(path)[1].lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(ext)
    if not mime:
        return ""
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return ('<image x="%.3f" y="%.3f" width="%.3f" height="%.3f" preserveAspectRatio="xMidYMid meet" '
            'xlink:href="data:%s;base64,%s"/>' % (x, y, w, h, mime, data))


# --------------------------------------------------------------------------- PDF

def _pdf_font():
    """Helvetica has no glyphs outside Latin-1 for some symbols; use DejaVu when available."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        for path in (r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if os.path.isfile(path):
                if "DGSans" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("DGSans", path))
                return "DGSans"
    except Exception:
        pass
    return "Helvetica"


# characters outside the glyph sets of Arial / Helvetica, replaced for the PDF
_PDF_SUBST = {"\u2300": "\u00d8", "\u2205": "\u00d8"}
_HELVETICA_SUBST = {"\u2013": "-", "\u2014": "-", "\u2264": "<=", "\u2265": ">=", "\u2191": "^", "\u2193": "v"}


def _pdf_safe(t, font):
    for a, b in _PDF_SUBST.items():
        t = t.replace(a, b)
    if font == "Helvetica":
        for a, b in _HELVETICA_SUBST.items():
            t = t.replace(a, b)
        t = t.encode("latin-1", "replace").decode("latin-1")
    return t


def to_pdf(drawings, cfg):
    """One PDF page per drawing. Returns bytes."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    L = _layers(cfg)
    font = _pdf_font()
    for d in drawings:
        W, H = d["size"]
        c.setPageSize((W * mm, H * mm))
        c.setTitle(d["values"].get("Title", d["name"]))
        c.saveState()
        c.scale(mm, mm)
        c.setLineCap(1)
        cur = [None]

        def style(layer):
            if cur[0] == layer:
                return
            st = style_of(L, layer)
            c.setLineWidth(st["w"])
            c.setDash(st["dash"] or [])
            cur[0] = layer

        for p in flatten(d["prims"]):
            k = p[0]
            if k == "line":
                style(p[5])
                c.line(p[1], p[2], p[3], p[4])
            elif k == "circle":
                style(p[4])
                c.circle(p[1], p[2], p[3], stroke=1, fill=0)
            elif k == "arc":
                cx, cy, r, a0, a1, layer = p[1:]
                style(layer)
                span = (a1 - a0) % 360.0 or 360.0
                path = c.beginPath()
                path.arc(cx - r, cy - r, cx + r, cy + r, startAng=a0, extent=span)
                c.drawPath(path, stroke=1, fill=0)
            elif k == "poly":
                style(p[2])
                pts = p[1]
                path = c.beginPath()
                path.moveTo(*pts[0])
                for q in pts[1:]:
                    path.lineTo(*q)
                if p[3]:
                    path.close()
                c.drawPath(path, stroke=1, fill=0)
            elif k == "solid":
                path = c.beginPath()
                path.moveTo(*p[1][0])
                for q in p[1][1:]:
                    path.lineTo(*q)
                path.close()
                c.drawPath(path, stroke=0, fill=1)
            elif k in ("text", "rtext"):
                x, y, h, t, anchor, ang = _text_args(p)
                if not t:
                    continue
                t = _pdf_safe(t, font)
                c.saveState()
                c.translate(x, y)
                if abs(ang) > 1e-9:
                    c.rotate(ang)
                c.setFont(font, h * CAP_TO_EM)
                if anchor == "middle":
                    c.drawCentredString(0, 0, t)
                elif anchor == "end":
                    c.drawRightString(0, 0, t)
                else:
                    c.drawString(0, 0, t)
                c.restoreState()
            elif k == "image":
                x, y, w, h, path = p[1:]
                try:
                    c.drawImage(ImageReader(path), x, y, w, h, preserveAspectRatio=True, anchor="c", mask="auto")
                except Exception:
                    pass
        c.restoreState()
        c.showPage()
    c.save()
    return buf.getvalue()


# --------------------------------------------------------------------------- DXF

def to_dxf(d, cfg):
    """DXF R2010, mm, one layer per line type. Returns bytes."""
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 1.0
    doc.linetypes.add("ISO_HIDDEN", pattern=[sum(DASH["hidden"]), DASH["hidden"][0], -DASH["hidden"][1]],
                      description="Hidden __ __ __")
    ch = DASH["chain"]
    doc.linetypes.add("ISO_CHAIN", pattern=[sum(ch), ch[0], -ch[1], 0.0, -(ch[1] + ch[2])],
                      description="Chain ____ . ____")
    L = _layers(cfg)
    ltype = {"hidden": "ISO_HIDDEN", "chain": "ISO_CHAIN"}
    for name, st in L.items():
        doc.layers.add(name.upper(), lineweight=int(round(st["w"] * 100)), linetype=ltype.get(name, "Continuous"))
    msp = doc.modelspace()
    align = {"start": TextEntityAlignment.LEFT, "middle": TextEntityAlignment.CENTER,
             "end": TextEntityAlignment.RIGHT}
    for p in d["prims"]:
        in_group = p[0] == "group"
        for q in (p[2] if in_group else [p]):
            k = q[0]
            lay = (lambda name: "DIM") if in_group else (lambda name: name.upper())
            if k == "line":
                msp.add_line((q[1], q[2]), (q[3], q[4]), dxfattribs={"layer": lay(q[5])})
            elif k == "circle":
                msp.add_circle((q[1], q[2]), q[3], dxfattribs={"layer": lay(q[4])})
            elif k == "arc":
                msp.add_arc((q[1], q[2]), q[3], q[4], q[5], dxfattribs={"layer": lay(q[6])})
            elif k == "poly":
                msp.add_lwpolyline(q[1], close=bool(q[3]), dxfattribs={"layer": lay(q[2])})
            elif k == "solid":
                pts = q[1]
                r = pts if len(pts) == 4 else [pts[0], pts[1], pts[2], pts[2]]
                msp.add_solid([r[0], r[1], r[3], r[2]], dxfattribs={"layer": lay(q[2])})
            elif k in ("text", "rtext"):
                x, y, h, t, anchor, ang = _text_args(q)
                if not t:
                    continue
                txt = msp.add_text(t, height=h, rotation=ang,
                                   dxfattribs={"layer": "DIM" if in_group else "TEXT"})
                txt.set_placement((x, y), align=align[anchor])
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")

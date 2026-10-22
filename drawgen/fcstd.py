# -*- coding: utf-8 -*-
"""FreeCAD document (.FCStd) with a TechDraw page.

The document holds the part as a Part::Feature, an SVG template with
editable title block fields and TechDraw views (Front, Top, Right, section,
isometric) at the same sheet, scale and positions as the PDF. Views are
computed by TechDraw when the document is opened, so dimensions can be
attached to the view geometry.
"""
import io
import os
import tempfile
import uuid
import zipfile
from xml.sax.saxutils import escape, quoteattr

from . import project as pj

FC_NS = "http://www.freecad.org/wiki/index.php?title=Svg_Namespace"
CAP_TO_EM = 1.0 / 0.72


# --------------------------------------------------------------------------- template

def template_svg(d, cfg):
    """SVG template: frame and title block, field values as freecad:editable texts."""
    W, H = d["size"]
    lw = cfg["line_widths_mm"]
    font = escape(cfg["title_block"].get("font", "osifont"))
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" xmlns:freecad="%s" version="1.1" '
           'width="%gmm" height="%gmm" viewBox="0 0 %g %g">' % (FC_NS, W, H, W, H)]
    widths = {"frame": lw["frame"], "title": lw["title"], "chain": lw["chain"]}

    def Y(y):
        return H - y

    for p in d["template_prims"]:
        k = p[0]
        if k == "line":
            dash = ' stroke-dasharray="6,0.75,0.15,0.75"' if p[5] == "chain" else ""
            out.append('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" stroke="#000" stroke-width="%.2f"%s/>'
                       % (p[1], Y(p[2]), p[3], Y(p[4]), widths.get(p[5], 0.35), dash))
        elif k == "circle":
            out.append('<circle cx="%.3f" cy="%.3f" r="%.3f" fill="none" stroke="#000" stroke-width="%.2f"/>'
                       % (p[1], Y(p[2]), p[3], widths.get(p[4], 0.35)))
        elif k == "poly":
            pts = " ".join("%.3f,%.3f" % (x, Y(y)) for x, y in p[1])
            tag = "polygon" if p[3] else "polyline"
            out.append('<%s points="%s" fill="none" stroke="#000" stroke-width="%.2f"/>'
                       % (tag, pts, widths.get(p[2], 0.35)))
        elif k == "text":
            x, y, h, t, layer, anchor = p[1:7]
            key = p[7] if len(p) > 7 else None
            if key:
                out.append('<text freecad:editable=%s x="%.3f" y="%.3f" font-family="%s" font-size="%.3f" '
                           'fill="#000"><tspan>%s</tspan></text>'
                           % (quoteattr(key), x, Y(y), font, h * CAP_TO_EM, escape(t)))
            elif t:
                out.append('<text x="%.3f" y="%.3f" font-family="%s" font-size="%.3f" text-anchor="%s" fill="#000">'
                           '%s</text>' % (x, Y(y), font, h * CAP_TO_EM, anchor, escape(t)))
    out.append("</svg>")
    return "\n".join(out)


# 45 deg hatch tile for TechDraw SvgHatch (64 x 64 units, line spacing 16 units)
_HATCH_STYLE = ("fill:none;stroke:#000000;stroke-width:1px;stroke-linecap:butt;"
                "stroke-linejoin:miter;stroke-opacity:1")
HATCH_SVG = (
    '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
    '<svg xmlns:svg="http://www.w3.org/2000/svg" xmlns="http://www.w3.org/2000/svg" '
    'height="64" width="64" version="1.1" id="hatch45">\n'
    '<defs id="defs1"><pattern height=".1" width=".1" y="0" x="0" patternUnits="userSpaceOnUse" id="hatch">'
    '<g style="fill:none;stroke:#000000;stroke-width:0.005"><path d="M0,0 l.12,.12"/></g>'
    '</pattern></defs>\n'
    + "".join('<path id="p%d" d="M %d,%d %d,%d" style="%s"/>\n' % ((i,) + seg + (_HATCH_STYLE,)) for i, seg in enumerate([
        (64, 0, 0, 64), (48, 0, 0, 48), (32, 0, 0, 32), (16, 0, 0, 16),
        (16, 64, 64, 16), (32, 64, 64, 32), (48, 64, 64, 48)]))
    + "</svg>")


# --------------------------------------------------------------------------- XML properties

def _vec(v):
    return '<PropertyVector valueX="%.12f" valueY="%.12f" valueZ="%.12f"/>' % tuple(float(c) for c in v)


def _prop(name, ptype, body):
    return '<Property name="%s" type="%s">%s</Property>' % (name, ptype, body)


def P_str(name, v, ptype="App::PropertyString"):
    return _prop(name, ptype, '<String value=%s/>' % quoteattr(str(v)))


def P_bool(name, v):
    return _prop(name, "App::PropertyBool", '<Bool value="%s"/>' % ("true" if v else "false"))


def P_float(name, v, ptype):
    return _prop(name, ptype, '<Float value="%.12f"/>' % float(v))


def P_int(name, v, ptype="App::PropertyInteger"):
    return _prop(name, ptype, '<Integer value="%d"/>' % int(v))


def P_vec(name, v):
    return _prop(name, "App::PropertyVector", _vec(v))


def P_link(name, target):
    return _prop(name, "App::PropertyLink", '<Link value=%s/>' % quoteattr(target))


def P_links(name, targets):
    body = '<LinkList count="%d">%s</LinkList>' % (len(targets), "".join('<Link value=%s/>' % quoteattr(t)
                                                                          for t in targets))
    return _prop(name, "App::PropertyLinkList", body)


def P_strlist(name, items):
    body = '<StringList count="%d">%s</StringList>' % (len(items), "".join('<String value=%s/>' % quoteattr(s)
                                                                            for s in items))
    return _prop(name, "App::PropertyStringList", body)


def P_map(name, d):
    body = '<Map count="%d">%s</Map>' % (len(d), "".join('<Item key=%s value=%s/>' % (quoteattr(k), quoteattr(str(v)))
                                                          for k, v in d.items()))
    return _prop(name, "App::PropertyMap", body)


def P_file_included(name, fname):
    return _prop(name, "App::PropertyFileIncluded", '<FileIncluded file=%s/>' % quoteattr(fname))


def P_shape(name, fname):
    return _prop(name, "Part::PropertyPartShape", '<Part file=%s/>' % quoteattr(fname))


# --------------------------------------------------------------------------- GUI document

BLACK = 255                # App::PropertyColor packing 0xRRGGBBAA


def gui_document(objects):
    """View provider settings: black hatch on white cut surface, 3D part hidden."""
    vps = []
    for name, typ, _, _, _ in objects:
        props = []
        if typ == "Part::Feature":
            props.append(P_bool("Visibility", False))
        if typ == "TechDraw::DrawViewSection":
            props += [_prop("HatchColor", "App::PropertyColor", '<PropertyColor value="%d"/>' % BLACK),
                      _prop("GeomHatchColor", "App::PropertyColor", '<PropertyColor value="%d"/>' % BLACK)]
        if props:
            vps.append('<ViewProvider name="%s" expanded="0"><Properties Count="%d" TransientCount="0">%s'
                       '</Properties></ViewProvider>' % (name, len(props), "".join(props)))
    return ('<?xml version="1.0" encoding="utf-8"?>\n<Document SchemaVersion="1" HasExpansion="1">'
            '<ViewProviderData Count="%d">%s</ViewProviderData></Document>' % (len(vps), "".join(vps)))


# --------------------------------------------------------------------------- document

def _view_part(name, label, src, direction, xdir, x, y, scale, hidden, smooth):
    return [
        P_str("Label", label),
        P_links("Source", [src]),
        P_vec("Direction", direction),
        P_vec("XDirection", xdir),
        P_int("ScaleType", 2, "App::PropertyEnumeration"),
        P_float("Scale", scale, "App::PropertyFloatConstraint"),
        P_float("X", x, "App::PropertyDistance"),
        P_float("Y", y, "App::PropertyDistance"),
        P_bool("HardHidden", hidden),
        P_bool("SmoothVisible", smooth),
        P_bool("CoarseView", False),
    ]


def build(d, cfg, shape, part_label):
    """Return .FCStd bytes for a composed drawing d and its shape."""
    m = d["meta"]
    s = d["scale"]
    W, H = d["size"]
    src = "Part"
    objects = []        # (name, type, props, deps, extension)
    objects.append((src, "Part::Feature", [P_str("Label", part_label), P_shape("Shape", "Part.Shape.brp")], [], False))

    vals = d["values"]
    objects.append(("Template", "TechDraw::DrawSVGTemplate", [
        P_str("Label", "Template"),
        P_file_included("PageResult", "Template.svg"),
        P_str("Template", "Template.svg", "App::PropertyFile"),
        P_map("EditableTexts", {k: v for k, v in vals.items()}),
        P_float("Width", W, "App::PropertyLength"),
        P_float("Height", H, "App::PropertyLength"),
    ], [], False))

    views = []
    hid, smo = m["hidden"], m["smooth"]
    c = m["centres"]
    names = {"front": "Front", "top": "Top", "right": "Right", "iso": "Isometric"}
    for key in ("front", "top", "right", "iso"):
        if key not in c:
            continue
        nm = names[key]
        direction, xdir = pj.VIEWS[key]
        sc = s * (m["iso_factor"] if key == "iso" else 1.0)
        objects.append((nm, "TechDraw::DrawViewPart",
                        _view_part(nm, nm, src, direction, xdir, c[key][0], c[key][1], sc,
                                   hid and key != "iso", smo), [src], True))
        views.append(nm)
    if "section" in c:
        sym = m["section_symbol"]
        sname = "Section"
        axis, offset, flip, sd, sx, base = m["section"]
        bdir, bxd = pj.VIEWS[base]
        _, bx_ax, by_ax = pj.frame(bdir, bxd)
        look = (-sd[0], -sd[1], -sd[2])
        a2 = (pj._dot(look, bx_ax), pj._dot(look, by_ax))
        sdir = 0 if a2[0] > 0.5 else 1 if a2[0] < -0.5 else 2 if a2[1] > 0.5 else 3
        base_name = names[base]
        props = _view_part(sname, "Section %s-%s" % (sym, sym), src, sd, sx,
                           c["section"][0], c["section"][1], s, False, smo)
        props += [
            P_link("BaseView", base_name),
            P_vec("SectionOrigin", m["origin"]),
            P_vec("SectionNormal", sd),
            P_int("SectionDirection", sdir, "App::PropertyEnumeration"),
            P_str("SectionSymbol", sym),
            P_int("CutSurfaceDisplay", 1, "App::PropertyEnumeration"),
            P_file_included("SvgIncluded", "Hatch.svg"),
            P_float("HatchScale", 1.0, "App::PropertyFloat"),
            P_bool("FuseBeforeCut", False),
            P_bool("TrimAfterCut", False),
        ]
        objects.append((sname, "TechDraw::DrawViewSection", props, [base_name, src], True))
        views.append(sname)
        cap = "SectionCaption"
        objects.append((cap, "TechDraw::DrawViewAnnotation", [
            P_str("Label", "Section caption"),
            P_strlist("Text", ["%s-%s" % (sym, sym)]),
            P_float("TextSize", m["text_height"], "App::PropertyLength"),
            P_float("X", c["section"][0], "App::PropertyDistance"),
            P_float("Y", m["section_caption_y"] + m["text_height"] / 2.0, "App::PropertyDistance"),
        ], [], False))
        views.append(cap)

    objects.insert(1, ("Page", "TechDraw::DrawPage", [
        P_str("Label", d.get("file_name") or "Page"),
        P_link("Template", "Template"),
        P_links("Views", views),
        P_bool("KeepUpdated", True),
        P_int("ProjectionType", 0 if m["first_angle"] else 1, "App::PropertyEnumeration"),
        P_float("Scale", s, "App::PropertyFloatConstraint"),
    ], ["Template"] + views, False))

    x = ['<?xml version="1.0" encoding="utf-8"?>',
         '<Document SchemaVersion="4" ProgramVersion="1.0R39319 (Git)" FileVersion="1">',
         '<Properties Count="3" TransientCount="0">',
         P_str("Label", d.get("file_name") or part_label),
         P_str("Comment", "Created by SHINYCAD"),
         _prop("Uid", "App::PropertyUUID", '<Uuid value="%s"/>' % uuid.uuid4()),
         '</Properties>',
         '<Objects Count="%d" Dependencies="1">' % len(objects)]
    for name, _, _, deps, _ in objects:
        x.append('<ObjectDeps Name="%s" Count="%d">%s</ObjectDeps>'
                 % (name, len(deps), "".join('<Dep Name="%s"/>' % dd for dd in deps)))
    for i, (name, typ, _, _, _) in enumerate(objects):
        x.append('<Object type="%s" name="%s" id="%d" Touched="1"/>' % (typ, name, 1000 + i))
    x.append('</Objects>')
    x.append('<ObjectData Count="%d">' % len(objects))
    for name, typ, props, _, ext in objects:
        x.append('<Object name="%s"%s>' % (name, ' Extensions="True"' if ext else ""))
        if ext:
            x.append('<Extensions Count="1"><Extension type="TechDraw::CosmeticExtension" '
                     'name="CosmeticExtension"></Extension></Extensions>')
        x.append('<Properties Count="%d" TransientCount="0">' % len(props))
        x += props
        x.append('</Properties></Object>')
    x.append('</ObjectData>')
    x.append('</Document>')
    doc_xml = "\n".join(x)

    fd, tmp = tempfile.mkstemp(suffix=".brp")
    os.close(fd)
    try:
        pj.write_brep(shape, tmp)
        with open(tmp, "rb") as f:
            brep = f.read()
    finally:
        os.remove(tmp)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Document.xml", doc_xml)
        z.writestr("Part.Shape.brp", brep)
        z.writestr("Template.svg", template_svg(d, cfg))
        z.writestr("GuiDocument.xml", gui_document(objects))
        z.writestr("Hatch.svg", HATCH_SVG)
    return buf.getvalue()

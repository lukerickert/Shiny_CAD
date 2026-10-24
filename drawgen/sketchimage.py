# -*- coding: utf-8 -*-
"""Reference images of sketches: storage in the images folder of the sketches, radial lens correction, perspective
correction and the corrected image file.

Pixel coordinates: u to the right, v down, (0, 0) at the upper-left corner of the image.
p: pixel of the stored image. q: lens-corrected pixel, q = c + (p - c) (1 + k1 r^2), c the image centre and r = |p - c| / R
with R the half diagonal. r: pixel of the corrected image file, r ~ H q (homography, 3 x 3)."""
import hashlib
import json
import math
import os
import re
import shutil

import numpy as np

BROWSER_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
IMPORT_EXT = BROWSER_EXT + (".tif", ".tiff")
K1_LIMIT = 0.4               # |k1| of the lens fit
MAX_SIDE = 8000              # px, corrected image
MAX_PIXELS = 40e6            # corrected image
CELL = 24                    # px, grid of the mesh transform


def images_dir(sketch_dir):
    return os.path.join(sketch_dir, "images")


def _safe(s):
    return re.sub(r"[^A-Za-z0-9_\-. ]+", "_", str(s or "")).strip(" _.") or "image"


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def image_size(path):
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def store(src, name, folder):
    """Copies the image file src into folder. EXIF orientation is applied to the pixels; TIFF is written as PNG.
    An existing file with the same content is used again. Returns (file name, width px, height px)."""
    from PIL import Image, ImageOps
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(name or "image.png"))
    ext = ext.lower()
    if ext not in IMPORT_EXT:
        raise ValueError("%s: not an image file (%s)" % (name, ", ".join(IMPORT_EXT)))
    stem = _safe(stem)
    with Image.open(src) as im:
        im.load()
        orient = im.getexif().get(0x0112, 1) if hasattr(im, "getexif") else 1
        tmp = os.path.join(folder, "_import" + (".png" if ext in (".tif", ".tiff") else ext))
        if ext in (".tif", ".tiff") or orient not in (None, 1):
            out = ImageOps.exif_transpose(im)
            if ext in (".tif", ".tiff"):
                ext = ".png"
                if out.mode not in ("RGB", "RGBA", "L", "LA"):
                    out = out.convert("RGBA")
                out.save(tmp)
            elif ext in (".jpg", ".jpeg"):
                out.convert("RGB").save(tmp, quality=95)
            else:
                out.save(tmp)
        else:
            shutil.copyfile(src, tmp)
    h = _sha1(tmp)
    n = 1
    while True:
        fname = stem + ext if n == 1 else "%s_%d%s" % (stem, n, ext)
        path = os.path.join(folder, fname)
        if not os.path.exists(path):
            os.replace(tmp, path)
            break
        if _sha1(path) == h:
            os.remove(tmp)
            break
        n += 1
    w, hh = image_size(path)
    return fname, w, hh


def find(folder, fname):
    """Path of an image file of the folder (the name without folder parts), or None."""
    fname = os.path.basename(fname or "")
    path = os.path.join(folder, fname)
    return path if fname and os.path.isfile(path) else None


# --------------------------------------------------------------------------- lens

def _centre(w, h):
    return np.array([w / 2.0, h / 2.0]), math.hypot(w, h) / 2.0


def undistort(p, k1, w, h):
    """Lens-corrected pixels q of image pixels p (n x 2)."""
    p = np.asarray(p, float).reshape(-1, 2)
    c, R = _centre(w, h)
    d = p - c
    r2 = (d * d).sum(1) / (R * R)
    return c + d * (1.0 + k1 * r2)[:, None]


def distort(q, k1, w, h):
    """Image pixels p of lens-corrected pixels q (n x 2): the inverse of undistort (Newton on the radius)."""
    q = np.asarray(q, float).reshape(-1, 2)
    c, R = _centre(w, h)
    d = q - c
    ru = np.sqrt((d * d).sum(1)) / R
    rd = ru.copy()
    if k1 != 0:
        for _ in range(30):
            f = rd + k1 * rd ** 3 - ru
            fp = 1.0 + 3.0 * k1 * rd * rd
            fp = np.where(np.abs(fp) < 1e-6, 1e-6, fp)
            step = f / fp
            rd = rd - step
            if np.max(np.abs(step)) < 1e-12:
                break
        rd = np.maximum(rd, 0.0)
    s = np.where(ru > 1e-15, rd / np.where(ru > 1e-15, ru, 1.0), 1.0)
    return c + d * s[:, None]


def _line_residuals(pts):
    """Perpendicular distances of the points from their total least squares line, and the length of the point set."""
    m = pts.mean(0)
    d = pts - m
    _, s, vt = np.linalg.svd(d, full_matrices=False)
    n = vt[-1]
    res = d @ n
    along = d @ vt[0]
    return res, float(along.max() - along.min())


def fit_k1(lines, w, h):
    """Radial coefficient k1 that makes each line of picked image pixels straight. lines: [[[u, v], ...], ...], at
    least 3 points per line. The objective sum((distance / line length)^2) does not depend on the image scale.
    Returns {"k1", "rms_before", "rms_after" (px), "lines", "points"}."""
    L = [np.asarray(l, float).reshape(-1, 2) for l in lines if len(l) >= 3]
    if not L:
        raise ValueError("at least one line of 3 points is needed")

    def obj(k):
        s = 0.0
        for pts in L:
            res, ln = _line_residuals(undistort(pts, k, w, h))
            s += float((res * res).sum()) / max(ln, 1e-9) ** 2
        return s

    ks = np.linspace(-K1_LIMIT, K1_LIMIT, 161)
    vals = [obj(k) for k in ks]
    i = int(np.argmin(vals))
    a, b = ks[max(i - 1, 0)], ks[min(i + 1, len(ks) - 1)]
    g = (math.sqrt(5) - 1) / 2
    x1, x2 = b - g * (b - a), a + g * (b - a)
    f1, f2 = obj(x1), obj(x2)
    for _ in range(60):
        if f1 < f2:
            b, x2, f2 = x2, x1, f1
            x1 = b - g * (b - a)
            f1 = obj(x1)
        else:
            a, x1, f1 = x1, x2, f2
            x2 = a + g * (b - a)
            f2 = obj(x2)
    k1 = (a + b) / 2

    def rms(k):
        r = np.concatenate([_line_residuals(undistort(pts, k, w, h))[0] for pts in L])
        return float(math.sqrt((r * r).mean()))

    return {"k1": float(k1), "rms_before": rms(0.0), "rms_after": rms(k1), "lines": len(L),
            "points": int(sum(len(p) for p in L))}


def lens_bounds(k1, w, h):
    """[umin, vmin, umax, vmax] of the lens-corrected image (its boundary mapped by undistort)."""
    t = np.linspace(0, 1, 101)
    edge = np.concatenate([np.c_[t * w, 0 * t], np.c_[t * w, 0 * t + h], np.c_[0 * t, t * h], np.c_[0 * t + w, t * h]])
    q = undistort(edge, k1, w, h)
    return [float(q[:, 0].min()), float(q[:, 1].min()), float(q[:, 0].max()), float(q[:, 1].max())]


# --------------------------------------------------------------------------- perspective

def _normalise(p):
    c = p.mean(0)
    d = float(np.sqrt(((p - c) ** 2).sum(1)).mean()) or 1.0
    f = math.sqrt(2) / d
    return np.array([[f, 0, -f * c[0]], [0, f, -f * c[1]], [0, 0, 1.0]])


def homography(src, dst):
    """3 x 3 matrix H with dst ~ H src: exact for 4 point pairs, least squares (normalised DLT) for more."""
    src, dst = np.asarray(src, float).reshape(-1, 2), np.asarray(dst, float).reshape(-1, 2)
    if len(src) < 4 or len(src) != len(dst):
        raise ValueError("at least 4 point pairs are needed")
    Ts, Td = _normalise(src), _normalise(dst)
    s = np.c_[src, np.ones(len(src))] @ Ts.T
    d = np.c_[dst, np.ones(len(dst))] @ Td.T
    rows = []
    for (x, y, _), (u, v, _) in zip(s, d):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, sv, vt = np.linalg.svd(np.array(rows))
    if sv[-2] < 1e-9 * sv[0]:
        raise ValueError("the points do not define a perspective (3 or more of them on one line)")
    H = np.linalg.inv(Td) @ vt[-1].reshape(3, 3) @ Ts
    w = (H @ np.r_[src.mean(0), 1.0])[2]                # w > 0 at the points
    return H / (abs(H[2, 2]) if abs(H[2, 2]) > 1e-12 else 1.0) * (1.0 if w > 0 else -1.0)


def apply_h(H, pts):
    pts = np.asarray(pts, float).reshape(-1, 2)
    x = np.c_[pts, np.ones(len(pts))] @ np.asarray(H, float).T
    return x[:, :2] / x[:, 2:3], x[:, 2]


def _area(p):
    p = np.asarray(p, float)
    return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def fit_points(src, dst, bounds, reach=5.0):
    """Perspective correction from control points: src lens-corrected pixels q, dst their sketch points (mm, y up),
    at least 4 pairs. The corrected image has k px per mm (the pixel density of the picked points), u along the
    sketch x axis and v against the sketch y axis; dst[0] is at pixel c1. bounds: [umin, vmin, umax, vmax] of the
    lens-corrected image. Returns {"H": q -> corrected pixel, "out": [w, h] px, "k", "c1", "clipped" (the corrected
    image is cut to (1 + 2 reach) x the extent of the points), "rms", "max" (mm, deviation of the points after the fit)}."""
    src, dst = np.asarray(src, float).reshape(-1, 2), np.asarray(dst, float).reshape(-1, 2)
    if len(src) < 4 or len(src) != len(dst):
        raise ValueError("at least 4 point pairs are needed")
    ss = float(((src - src.mean(0)) ** 2).sum())
    ds = float(((dst - dst.mean(0)) ** 2).sum())
    if ss < 1e-9 or ds < 1e-12:
        raise ValueError("the points coincide")
    k = math.sqrt(ss / ds)
    t = (dst - dst[0]) * np.array([k, -k])
    H0 = homography(src, t)
    m, wz = apply_h(H0, src)
    if np.any(wz <= 0):
        raise ValueError("the points do not define a perspective (check the order of the points)")
    dev = np.sqrt(((m - t) ** 2).sum(1)) / k
    u0, v0, u1, v1 = bounds
    g = np.linspace(0, 1, 41)
    box = np.concatenate([np.c_[u0 + g * (u1 - u0), 0 * g + v0], np.c_[u0 + g * (u1 - u0), 0 * g + v1],
                          np.c_[0 * g + u0, v0 + g * (v1 - v0)], np.c_[0 * g + u1, v0 + g * (v1 - v0)]])
    mb, wb = apply_h(H0, box)
    tb = [float(t[:, 0].min()), float(t[:, 1].min()), float(t[:, 0].max()), float(t[:, 1].max())]
    ext = max(tb[2] - tb[0], tb[3] - tb[1])
    rb = [tb[0] - reach * ext, tb[1] - reach * ext, tb[2] + reach * ext, tb[3] + reach * ext]
    clipped = bool(np.any(wb <= 0))
    if clipped:
        b = rb
    else:
        b = [float(mb[:, 0].min()), float(mb[:, 1].min()), float(mb[:, 0].max()), float(mb[:, 1].max())]
        if b[0] < rb[0] or b[1] < rb[1] or b[2] > rb[2] or b[3] > rb[3]:
            clipped = True
            b = [max(b[0], rb[0]), max(b[1], rb[1]), min(b[2], rb[2]), min(b[3], rb[3])]
    bw, bh = b[2] - b[0], b[3] - b[1]
    if bw <= 0 or bh <= 0:
        raise ValueError("the corrected image is empty")
    f = min(1.0, MAX_SIDE / bw, MAX_SIDE / bh, math.sqrt(MAX_PIXELS / (bw * bh)))
    T = np.array([[f, 0, -f * b[0]], [0, f, -f * b[1]], [0, 0, 1.0]])
    H = T @ H0
    H = H / H[2, 2]
    return {"H": H.tolist(), "out": [int(math.ceil(bw * f)), int(math.ceil(bh * f))], "k": k * f,
            "c1": [-f * b[0], -f * b[1]], "clipped": clipped, "rms": float(math.sqrt((dev ** 2).mean())),
            "max": float(dev.max())}


def perspective(pts, width, height, bounds):
    """Perspective correction from the 4 corners of a rectangle width x height (mm), picked in order around it in
    lens-corrected pixels q (corner 1 to corner 2 along the width). The rectangle is placed with corner 1 at the
    sketch origin and corner 2 on the +x axis, turning the same way as the picks (no mirror image). Returns
    fit_points() of the corners."""
    pts = np.asarray(pts, float).reshape(-1, 2)
    if len(pts) != 4:
        raise ValueError("4 corner points are needed")
    if not (width > 0 and height > 0):
        raise ValueError("width and height must be > 0")
    a = _area(pts)
    if abs(a) < 1.0:
        raise ValueError("the 4 points do not enclose an area")

    def crs(p, q):
        return p[0] * q[1] - p[1] * q[0]
    s = [crs(pts[(i + 1) % 4] - pts[i], pts[(i + 2) % 4] - pts[(i + 1) % 4]) for i in range(4)]
    if not (all(x > 0 for x in s) or all(x < 0 for x in s)):
        raise ValueError("the 4 points are not in order around the rectangle (the quadrilateral is not convex)")
    sg = 1.0 if a > 0 else -1.0             # pixels v down: a > 0 turns clockwise on the screen
    dst = [(0, 0), (width, 0), (width, -sg * height), (0, -sg * height)]
    return fit_points(pts, dst, bounds)


def fit_ellipse(pts):
    """Conic matrix C (3 x 3, symmetric, x^T C x = 0 with x = [u, v, 1]) of the ellipse fitted to at least 5 points
    (direct least squares fit restricted to ellipses, Halir and Flusser 1998)."""
    pts = np.asarray(pts, float).reshape(-1, 2)
    if len(pts) < 5:
        raise ValueError("at least 5 points on each circle are needed")
    T = _normalise(pts)
    x = np.c_[pts, np.ones(len(pts))] @ T.T
    u, v = x[:, 0], x[:, 1]
    D1 = np.c_[u * u, u * v, v * v]
    D2 = np.c_[u, v, np.ones(len(u))]
    S1, S2, S3 = D1.T @ D1, D1.T @ D2, D2.T @ D2
    if np.linalg.cond(S3) > 1e12:
        raise ValueError("the points of a circle are on one line")
    Tm = -np.linalg.solve(S3, S2.T)
    M = S1 + S2 @ Tm
    M = np.array([M[2] / 2, -M[1], M[0] / 2])
    w, V = np.linalg.eig(M)
    V = np.real(V)
    cond = 4 * V[0] * V[2] - V[1] ** 2
    ok = np.where(cond > 0)[0]
    if not len(ok):
        raise ValueError("no ellipse fits the points of a circle")
    a1 = V[:, ok[0]]
    a, b, c = a1
    d, e, f = Tm @ a1
    C = np.array([[a, b / 2, d / 2], [b / 2, c, e / 2], [d / 2, e / 2, f]])
    C = T.T @ C @ T
    return C / np.linalg.norm(C)


def _ellipse(C):
    """Centre x0, shape matrix M ((x - x0)^T M (x - x0) = 1) and semi-axes [a, b] (a >= b) of the conic C."""
    A, b = C[:2, :2], C[:2, 2]
    if np.linalg.det(A) <= 0:
        raise ValueError("the fitted conic is not an ellipse")
    x0 = -np.linalg.solve(A, b)
    g = C[2, 2] - x0 @ A @ x0
    M = A / -g
    w = np.linalg.eigvalsh(M)
    if np.any(w <= 0):
        raise ValueError("the fitted conic is not an ellipse")
    return x0, M, [float(1 / math.sqrt(w[0])), float(1 / math.sqrt(w[1]))]


def _inside(C, p):
    x0 = _ellipse(C)[0]
    s = lambda q: float(np.r_[q, 1.0] @ C @ np.r_[q, 1.0])
    return s(p) * s(x0) > 0


def _concentric_centre(C1, C2):
    """Image of the common centre of two concentric circles in one plane from their ellipses C1, C2: the pencil
    C1 - l C2 holds the double line at infinity; its pole with respect to C1 is the centre."""
    w = np.linalg.eigvals(np.linalg.solve(C2, C1))
    i, j = min(((0, 1), (0, 2), (1, 2)), key=lambda ij: abs(w[ij[0]] - w[ij[1]]))
    lam = float(np.real(w[i] + w[j]) / 2)
    D = C1 - lam * C2
    D = (D + D.T) / 2
    ev, V = np.linalg.eigh(D)
    line = V[:, int(np.argmax(np.abs(ev)))]
    c = np.linalg.solve(C1, line)
    if abs(c[2]) < 1e-12 * np.linalg.norm(c):
        raise ValueError("the two ellipses do not give a centre (are the circles concentric?)")
    return c[:2] / c[2]


def _sqrtm(M):
    w, V = np.linalg.eigh(M)
    return V @ np.diag(np.sqrt(w)) @ V.T


def _round_h(C, c, persp, R, N):
    """q -> plane (mm, v down) of the circle C (normalised coordinates N) with the centre image c: perspective
    (polar of c as the vanishing line) or affine, ellipse -> circle of radius R at 0, image u axis along +x."""
    Tc = np.array([[1, 0, -c[0]], [0, 1, -c[1]], [0, 0, 1.0]])
    P = np.eye(3)
    if persp:
        ln = np.linalg.inv(Tc).T @ (C @ np.r_[c, 1.0])              # polar of the centre: the vanishing line
        P[2] = ln / ln[2]
    G = P @ Tc
    Gi = np.linalg.inv(G)
    C1 = Gi.T @ C @ Gi
    x0, M, _ = _ellipse(C1 / np.linalg.norm(C1))
    L = R * _sqrtm(M)
    Hr = np.r_[np.c_[L, -L @ x0], [[0, 0, 1.0]]] @ G @ N
    cq = apply_h(np.linalg.inv(N), [c])[0][0]
    m, _ = apply_h(Hr, [cq, cq + [1.0, 0.0]])
    d = m[1] - m[0]
    t = math.atan2(d[1], d[0])
    Rt = np.array([[math.cos(t), math.sin(t), 0], [-math.sin(t), math.cos(t), 0], [0, 0, 1.0]])
    return Rt @ Hr


def _scale_variation(Hr, C, N):
    """(max - min) / mean of the linear scale of Hr at 16 points of the ellipse C (normalised coordinates N)."""
    x0, M, _ = _ellipse(C)
    w, V = np.linalg.eigh(M)
    a = np.linspace(0, 2 * math.pi, 16, endpoint=False)
    p = apply_h(np.linalg.inv(N), x0 + np.c_[np.cos(a) / math.sqrt(w[0]), np.sin(a) / math.sqrt(w[1])] @ V.T)[0]
    H = np.asarray(Hr, float)
    s = []
    for x, y in p:
        h = H @ [x, y, 1.0]
        J = (H[:2, :2] * h[2] - np.outer(h[:2], H[2, :2])) / h[2] ** 2
        s.append(math.sqrt(abs(np.linalg.det(J))))
    s = np.array(s)
    return float((s.max() - s.min()) / s.mean())


def round_part(rims, diameter, bounds, centre=None):
    """Correction from a round part: rims = 1 or 2 lists of at least 5 points (lens-corrected pixels q) on circles
    of one plane (2 lists: concentric circles), diameter (mm) of the first circle, centre = the picked image of the
    circle centre or None (not used with 2 circles when outside circle 1: "centre_unused"). Correction: perspective
    from the centre (picked, else from 2 concentric circles), else
    affine (the ellipse becomes a circle). A perspective correction that changes the scale across circle 1 by more
    than the ellipse shape allows is replaced by the affine one ("rejected": the reason). The circle centre is dst[0] at the sketch origin; the image u axis at the
    centre stays along the sketch x axis. Returns fit_points() of points of the corrected circle with "mode"
    ("affine", "centre", "concentric"), "cq" (centre, q), "axes" (semi-axes px of ellipse 1), "d2" (mm, diameter of
    circle 2) and "rms", "max" (mm, radial deviation of the rim points from the circles)."""
    rims = [np.asarray(r, float).reshape(-1, 2) for r in (rims or []) if r is not None and len(r)]
    if not rims or len(rims) > 2:
        raise ValueError("points on 1 or 2 circles are needed")
    if not (diameter and diameter > 0):
        raise ValueError("diameter must be > 0")
    N = _normalise(np.concatenate(rims))
    Ni = np.linalg.inv(N)
    Cs = [Ni.T @ fit_ellipse(r) @ Ni for r in rims]              # conics in normalised coordinates
    Cs = [C / np.linalg.norm(C) for C in Cs]
    axes = [a / N[0, 0] for a in _ellipse(Cs[0])[2]]
    unused, rejected = False, None
    if centre is not None:
        c = apply_h(N, [centre])[0][0]
        if not _inside(Cs[0], c):
            if len(rims) < 2:
                raise ValueError("the picked centre is outside circle 1")
            unused, centre = True, None
    x1 = _ellipse(Cs[0])[0]
    if centre is not None:
        mode = "centre"
    elif len(rims) == 2:
        mode = "concentric"
        try:
            c = _concentric_centre(Cs[0], Cs[1])
            if not (_inside(Cs[0], c) and _inside(Cs[1], c)):
                raise ValueError
        except (ValueError, np.linalg.LinAlgError):
            mode, c, rejected = "affine", x1, "the two ellipses give no common centre"
    else:
        mode, c = "affine", x1
    R = diameter / 2.0
    Hr = _round_h(Cs[0], c, mode != "affine", R, N)
    ratio = axes[1] / axes[0]
    if mode != "affine":
        # scale change of the correction across circle 1, against the largest the ellipse shape allows (plane tilt
        # with cos(tilt) = axis ratio, circle diameter up to the camera distance)
        var = _scale_variation(Hr, Cs[0], N)
        allowed = math.sqrt(max(0.0, 1 - ratio * ratio)) + 0.02
        if var > allowed:
            rejected = ("the %s gives a scale change of %.0f %% across circle 1, the ellipse shape (axis ratio %.3f) "
                        "allows %.0f %%" % ("picked centre" if mode == "centre" else "pair of circles", 100 * var,
                                            ratio, 100 * allowed))
            mode, c = "affine", x1
            Hr = _round_h(Cs[0], c, False, R, N)
    cq = apply_h(np.linalg.inv(N), [c])[0][0]
    devs, d2 = [], None
    for i, r in enumerate(rims):
        p, wz = apply_h(Hr, r)
        if np.any(wz <= 0):
            raise ValueError("rim points beyond the vanishing line (check the points and the centre)")
        rr = np.sqrt((p ** 2).sum(1))
        if i == 0:
            devs.append(rr - R)
        else:
            d2 = float(2 * rr.mean())
            devs.append(rr - rr.mean())
    dev = np.abs(np.concatenate(devs))
    ang = np.linspace(0, 2 * math.pi, 24, endpoint=False)
    circ = np.c_[R * np.cos(ang), R * np.sin(ang)]
    src = np.r_[[cq], apply_h(np.linalg.inv(Hr), circ)[0]]
    dst = np.r_[[[0.0, 0.0]], circ * [1, -1]]
    out = fit_points(src, dst, bounds)
    out.update({"mode": mode, "cq": [float(cq[0]), float(cq[1])], "axes": axes, "d2": d2, "centre_unused": unused,
                "rejected": rejected,
                "rms": float(math.sqrt((dev ** 2).mean())), "max": float(dev.max())})
    return out


# --------------------------------------------------------------------------- corrected image

def corrected_name(fname, k1, H, out):
    key = json.dumps([fname, round(float(k1 or 0), 9), [[round(float(x), 9) for x in r] for r in H] if H else None,
                      list(out or [])])
    stem, ext = os.path.splitext(fname)
    ext = ".png" if ext.lower() in (".png", ".gif", ".webp", ".bmp") else ".jpg"
    return "%s_c%s%s" % (stem, hashlib.sha1(key.encode()).hexdigest()[:10], ext)


def render(src, k1, H, out, dst):
    """Writes the corrected image dst (out[0] x out[1] px): each pixel r is taken from the image pixel
    p = distort(H^-1 r). PNG with transparent pixels outside the image, JPEG with white."""
    from PIL import Image
    ow, oh = int(out[0]), int(out[1])
    if ow < 1 or oh < 1 or ow > MAX_SIDE or oh > MAX_SIDE or ow * oh > MAX_PIXELS:
        raise ValueError("corrected image size %d x %d px out of range" % (ow, oh))
    Hi = np.linalg.inv(np.asarray(H, float))
    png = dst.lower().endswith(".png")
    with Image.open(src) as im:
        im.load()
        w, h = im.size
        im = im.convert("RGBA" if png else "RGB")
        xs = np.arange(0, ow + CELL, CELL, dtype=float)
        ys = np.arange(0, oh + CELL, CELL, dtype=float)
        xs[-1], ys[-1] = min(xs[-1], ow), min(ys[-1], oh)
        xs, ys = np.unique(xs), np.unique(ys)
        gx, gy = np.meshgrid(xs, ys)
        g = np.c_[gx.ravel(), gy.ravel()]
        q, wz = apply_h(Hi, g)
        p = distort(q, k1, w, h)
        ok = (wz > 0) & np.isfinite(p).all(1)
        P = p.reshape(len(ys), len(xs), 2)
        OK = ok.reshape(len(ys), len(xs))
        mesh = []
        for j in range(len(ys) - 1):
            for i in range(len(xs) - 1):
                if not (OK[j, i] and OK[j + 1, i] and OK[j + 1, i + 1] and OK[j, i + 1]):
                    continue
                quad = (*P[j, i], *P[j + 1, i], *P[j + 1, i + 1], *P[j, i + 1])
                if min(quad[0::2]) > w or max(quad[0::2]) < 0 or min(quad[1::2]) > h or max(quad[1::2]) < 0:
                    continue
                mesh.append(((int(xs[i]), int(ys[j]), int(xs[i + 1]), int(ys[j + 1])), tuple(float(x) for x in quad)))
        fill = (0, 0, 0, 0) if png else (255, 255, 255)
        res = im.transform((ow, oh), Image.Transform.MESH, mesh, resample=Image.Resampling.BILINEAR,
                               fillcolor=fill) if mesh else Image.new(im.mode, (ow, oh), fill)
    tmp = dst + ".tmp" + os.path.splitext(dst)[1]
    if png:
        res.save(tmp, optimize=False, compress_level=3)
    else:
        res.save(tmp, quality=92)
    os.replace(tmp, dst)
    return dst

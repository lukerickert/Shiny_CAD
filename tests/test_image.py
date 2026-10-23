# -*- coding: utf-8 -*-
"""Reference images of sketches (drawgen/sketchimage.py and the /api/sketch/image requests): lens model and fit,
homography, perspective correction from a rectangle and from control points, corrected image file, import."""
import io
import math

import numpy as np
import pytest

from drawgen import sketchimage as si

W, H = 1600, 1200


def test_undistort_distort_inverse():
    p = np.array([[0, 0], [W, H], [800, 600], [100, 1100], [1500, 50]], float)
    for k1 in (-0.2, 0.0, 0.15):
        q = si.undistort(p, k1, W, H)
        assert np.abs(si.distort(q, k1, W, H) - p).max() < 1e-8
    # the centre does not move; a corner moves by k1 times its distance from the centre
    assert np.allclose(si.undistort([[800, 600]], 0.1, W, H), [[800, 600]])
    assert np.allclose(si.undistort([[0, 0]], 0.1, W, H), [[-80, -60]])


def _lines(k1, hom=None):
    hom = np.eye(3) if hom is None else hom
    out = []
    for a, b in (((150, 120), (1450, 150)), ((130, 1080), (1480, 1050)), ((140, 130), (160, 1070))):
        t = np.linspace(0, 1, 7)[:, None]
        q, _ = si.apply_h(hom, np.array(a) * (1 - t) + np.array(b) * t)
        out.append(si.distort(q, k1, W, H).tolist())
    return out


@pytest.mark.parametrize("k1", [-0.12, -0.03, 0.05, 0.2])
def test_fit_k1(k1):
    r = si.fit_k1(_lines(k1), W, H)
    assert abs(r["k1"] - k1) < 1e-6
    assert r["rms_after"] < 1e-6 < r["rms_before"]
    assert r["lines"] == 3 and r["points"] == 21


def test_fit_k1_needs_3_points():
    with pytest.raises(ValueError):
        si.fit_k1([[[0, 0], [10, 0]]], W, H)


def test_lens_bounds():
    b = si.lens_bounds(0.1, W, H)
    assert b == pytest.approx([-80, -60, 1680, 1260])
    b = si.lens_bounds(-0.1, W, H)
    assert b[0] > 0 and b[2] < W


HOM = np.array([[4.2, 1.1, 300.0], [0.3, 3.0, 420.0], [0.0006, 0.0018, 1.0]])


def test_homography_exact_and_least_squares():
    src = np.array([[0, 0], [200, 0], [200, 100], [0, 100], [50, 30], [150, 80]], float)
    dst, _ = si.apply_h(HOM, src)
    for n in (4, 6):
        Hf = si.homography(src[:n], dst[:n])
        m, w = si.apply_h(Hf, src)
        assert np.abs(m - dst).max() < 1e-6 and (w > 0).all()
    with pytest.raises(ValueError):
        si.homography([[0, 0], [1, 0], [2, 0], [3, 0]], [[0, 0], [1, 0], [2, 0], [3, 0]])


def test_perspective_rectangle():
    rect = [(0, 0), (200, 0), (200, 100), (0, 100)]
    pts, _ = si.apply_h(HOM, rect)
    r = si.perspective(pts.tolist(), 200, 100, [0, 0, 2400, 2000])
    m, _ = si.apply_h(r["H"], pts)
    mm = (m - r["c1"]) / r["k"] * [1, -1]        # corrected pixels -> sketch mm (corner 1 at the origin)
    # the picks turn clockwise on the screen (pixels v down): the rectangle lies below the x axis
    assert np.abs(mm - [[0, 0], [200, 0], [200, -100], [0, -100]]).max() < 1e-6
    assert r["out"][0] <= si.MAX_SIDE and r["out"][1] <= si.MAX_SIDE
    # corners in the opposite order: rectangle above the x axis (no mirror image)
    r2 = si.perspective(pts[::-1].tolist(), 100, 200, [0, 0, 2400, 2000])
    m2, _ = si.apply_h(r2["H"], pts[::-1])
    mm2 = (m2 - r2["c1"]) / r2["k"] * [1, -1]
    assert np.abs(mm2 - [[0, 0], [100, 0], [100, 200], [0, 200]]).max() < 1e-6


def test_perspective_errors():
    with pytest.raises(ValueError, match="convex"):
        si.perspective([[0, 0], [100, 0], [30, 30], [0, 100]], 10, 10, [0, 0, 200, 200])
    with pytest.raises(ValueError):
        si.perspective([[0, 0], [100, 0], [100, 100]], 10, 10, [0, 0, 200, 200])


def test_fit_points_control_points():
    dst = np.array([[10, 20], [210, 20], [210, 120], [10, 120], [60, 50], [160, 100]], float)
    src, _ = si.apply_h(HOM, dst * [1, -1])            # sketch y up, the object seen from above
    r = si.fit_points(src.tolist(), dst.tolist(), [0, 0, 2400, 2000])
    m, _ = si.apply_h(r["H"], src)
    mm = (m - r["c1"]) / r["k"] * [1, -1] + dst[0]
    assert np.abs(mm - dst).max() < 1e-6
    assert r["rms"] < 1e-6
    # a moved point gives a deviation
    bad = dst.copy()
    bad[5] += [3, 0]
    r = si.fit_points(src.tolist(), bad.tolist(), [0, 0, 2400, 2000])
    assert 0.1 < r["max"] < 3


def test_render_scale_and_lens(tmp_path):
    from PIL import Image, ImageDraw
    src = tmp_path / "a.png"
    im = Image.new("RGB", (400, 300), (255, 255, 255))
    ImageDraw.Draw(im).rectangle([100, 100, 139, 139], fill=(255, 0, 0))
    im.save(src)
    dst = tmp_path / "b.png"
    si.render(str(src), 0.0, [[0.5, 0, 0], [0, 0.5, 0], [0, 0, 1]], [200, 150], str(dst))
    out = Image.open(dst)
    assert out.size == (200, 150) and out.mode == "RGBA"
    assert out.getpixel((60, 60))[:3] == (255, 0, 0)
    assert out.getpixel((40, 40))[:3] == (255, 255, 255)
    # lens: the red square moves to undistort() of its centre
    k1 = 0.2
    b = si.lens_bounds(k1, 400, 300)
    out_size = [math.ceil(b[2] - b[0]), math.ceil(b[3] - b[1])]
    si.render(str(src), k1, [[1, 0, -b[0]], [0, 1, -b[1]], [0, 0, 1]], out_size, str(dst))
    c = si.undistort([[120, 120]], k1, 400, 300)[0] - b[:2]
    out = Image.open(dst)
    assert out.getpixel((int(c[0]), int(c[1])))[:3] == (255, 0, 0)
    assert out.getpixel((out_size[0] // 2, 1))[3] == 0     # outside the image (middle of the top edge): transparent
    with pytest.raises(ValueError):
        si.render(str(src), 0, np.eye(3).tolist(), [si.MAX_SIDE + 1, 10], str(dst))


def test_store_exif_tiff_and_duplicates(tmp_path):
    from PIL import Image
    folder = tmp_path / "images"
    a = tmp_path / "photo.jpg"
    im = Image.new("RGB", (40, 20), (10, 200, 30))
    ex = im.getexif()
    ex[0x0112] = 6                                       # rotated 90 deg: stored as 20 x 40 px
    im.save(a, exif=ex)
    assert si.store(str(a), "photo.jpg", str(folder)) == ("photo.jpg", 20, 40)
    assert si.store(str(a), "photo.jpg", str(folder))[0] == "photo.jpg"     # same content: the same file
    b = tmp_path / "other.jpg"
    Image.new("RGB", (8, 8)).save(b)
    assert si.store(str(b), "photo.jpg", str(folder))[0] == "photo_2.jpg"
    t = tmp_path / "scan.tif"
    Image.new("L", (30, 10)).save(t)
    assert si.store(str(t), "scan.tif", str(folder)) == ("scan.png", 30, 10)
    with pytest.raises(ValueError):
        si.store(str(t), "notes.txt", str(folder))


def test_api_image_requests(client, tmp_path):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (W, H), (200, 200, 200)).save(buf, "PNG")
    r = client.post("/api/sketch/image", data={"file": (io.BytesIO(buf.getvalue()), "api photo.png")},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert (j["w"], j["h"]) == (W, H) and j["file"] == "api photo.png"
    assert j["path"].replace("\\", "/").endswith("work/images/api photo.png")
    f = j["file"]
    assert client.get("/api/sketch/image/file/" + f).status_code == 200
    assert client.get("/api/sketch/image/file/missing.png").status_code == 404
    r = client.post("/api/sketch/image/lens", json={"file": f, "lines": _lines(0.07)}).get_json()
    assert abs(r["k1"] - 0.07) < 1e-6 and len(r["bounds"]) == 4
    rect = [(0, 0), (200, 0), (200, 100), (0, 100)]
    pts, _ = si.apply_h(HOM, rect)
    p = client.post("/api/sketch/image/perspective", json={"file": f, "k1": 0, "pts": pts.tolist(), "width": 200, "height": 100}).get_json()
    assert set(p) >= {"H", "out", "k", "c1", "clipped"}
    assert client.post("/api/sketch/image/perspective", json={"file": f, "pts": pts[:3].tolist(), "width": 200, "height": 100}).status_code == 400
    c = client.post("/api/sketch/image/fit", json={"file": f, "src": pts.tolist(), "dst": [[0, 0], [200, 0], [200, -100], [0, -100]]}).get_json()
    assert c["rms"] < 1e-6
    r1 = client.post("/api/sketch/image/render", json={"file": f, "k1": 0, "H": p["H"], "out": p["out"]}).get_json()
    assert r1["file"].startswith("api photo_c") and r1["file"].endswith(".png")
    assert client.post("/api/sketch/image/render", json={"file": f, "k1": 0, "H": p["H"], "out": p["out"]}).get_json() == r1
    assert client.get("/api/sketch/image/file/" + r1["file"]).status_code == 200
    assert client.post("/api/sketch/image", json={"path": str(tmp_path / "none.png")}).status_code == 400

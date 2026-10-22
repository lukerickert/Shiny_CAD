// Coordinate system triad for the 3D views (Part and Assembly tabs): X red, Y green, Z blue, with labels,
// drawn on top of the model.
import * as THREE from "three";

function label(text, color) {
  const c = document.createElement("canvas");
  c.width = 64; c.height = 64;
  const g = c.getContext("2d");
  g.font = "bold 44px sans-serif";
  g.textAlign = "center"; g.textBaseline = "middle";
  g.fillStyle = color;
  g.fillText(text, 32, 34);
  const tex = new THREE.CanvasTexture(c);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, depthWrite: false, transparent: true }));
  sp.renderOrder = 1001;
  return sp;
}

/** Axes group of the given length (mm) at the origin. */
export function makeAxes(size) {
  const grp = new THREE.Group();
  grp.name = "axes";
  const axes = [[[1, 0, 0], 0xd32f2f, "X"], [[0, 1, 0], 0x2e7d32, "Y"], [[0, 0, 1], 0x1565c0, "Z"]];
  for (const [d, col, name] of axes) {
    const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(d[0] * size, d[1] * size, d[2] * size)]);
    const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: col, depthTest: false, depthWrite: false, transparent: true }));
    line.renderOrder = 1000;
    grp.add(line);
    const sp = label(name, "#" + col.toString(16).padStart(6, "0"));
    sp.position.set(d[0] * size * 1.12, d[1] * size * 1.12, d[2] * size * 1.12);
    sp.scale.set(size * 0.14, size * 0.14, 1);
    grp.add(sp);
  }
  return grp;
}

/** Replaces the axes of a scene with axes sized for a bounding box [x0, y0, z0, x1, y1, z1]. */
export function updateAxes(scene, bbox, visible) {
  const old = scene.getObjectByName("axes");
  if (old) scene.remove(old);
  if (!visible) return;
  const bb = bbox || [-50, -50, -50, 50, 50, 50];
  const size = Math.max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], 10) * 0.5;
  scene.add(makeAxes(size));
}

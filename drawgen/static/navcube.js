import * as THREE from "three";

// Navigation cube in the upper-right corner of a 3D view. The cube turns with the main camera; a click on a face
// turns the main camera to look at that face (front: looking along +Y with Z up, as in the drawing views).
// createNavCube(box, mainCamera, onView) -> { render(), dispose() }; onView(dir, up): dir is the direction from
// the target to the camera, up the camera up vector.

const FACES = [
  { n: [1, 0, 0], label: "Right", up: [0, 0, 1] },
  { n: [-1, 0, 0], label: "Left", up: [0, 0, 1] },
  { n: [0, 1, 0], label: "Back", up: [0, 0, 1] },
  { n: [0, -1, 0], label: "Front", up: [0, 0, 1] },
  { n: [0, 0, 1], label: "Top", up: [0, 1, 0] },
  { n: [0, 0, -1], label: "Bottom", up: [0, -1, 0] },
];

function faceTexture(label, hot) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  g.fillStyle = hot ? "#cfe0f5" : "#f3f5f8";
  g.fillRect(0, 0, 128, 128);
  g.strokeStyle = "#7a8794";
  g.lineWidth = 4;
  g.strokeRect(2, 2, 124, 124);
  g.fillStyle = "#2b4a6f";
  g.font = "bold 30px sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(label, 64, 64);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export function createNavCube(box, mainCamera, onView) {
  const size = 96;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(size, size);
  const el = renderer.domElement;
  el.className = "navcube";
  el.title = "Click a face to look at it";
  box.appendChild(el);
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-0.95, 0.95, 0.95, -0.95, 0.1, 10);
  const mats = FACES.map(f => new THREE.MeshBasicMaterial({ map: faceTexture(f.label, false) }));
  const hotMats = FACES.map(f => new THREE.MeshBasicMaterial({ map: faceTexture(f.label, true) }));
  // BoxGeometry material order: +x, -x, +y, -y, +z, -z (the same as FACES)
  const cube = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), mats.slice());
  scene.add(cube);
  scene.add(new THREE.LineSegments(new THREE.EdgesGeometry(cube.geometry), new THREE.LineBasicMaterial({ color: 0x4a5560 })));
  const ray = new THREE.Raycaster();
  let hot = -1;

  function render() {
    const d = mainCamera.position.clone().sub(mainCamera.userData.target || new THREE.Vector3()).normalize();
    if (!isFinite(d.x) || d.lengthSq() < 0.5) d.set(1, -1, 1).normalize();
    camera.position.copy(d.multiplyScalar(3));
    camera.up.copy(mainCamera.up);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  }

  function faceAt(e) {
    const r = el.getBoundingClientRect();
    const p = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(p, camera);
    const hit = ray.intersectObject(cube)[0];
    return hit ? Math.floor(hit.faceIndex / 2) : -1;
  }

  el.addEventListener("pointermove", e => {
    const i = faceAt(e);
    if (i === hot) return;
    if (hot >= 0) cube.material[hot] = mats[hot];
    hot = i;
    if (hot >= 0) cube.material[hot] = hotMats[hot];
    el.style.cursor = hot >= 0 ? "pointer" : "default";
    render();
  });
  el.addEventListener("pointerleave", () => { if (hot >= 0) cube.material[hot] = mats[hot]; hot = -1; render(); });
  el.addEventListener("pointerdown", e => { e.stopPropagation(); e.preventDefault(); });
  el.addEventListener("pointerup", e => {
    e.stopPropagation();
    const i = faceAt(e);
    if (i < 0) return;
    const f = FACES[i];
    onView(new THREE.Vector3(...f.n), new THREE.Vector3(...f.up));
  });
  el.addEventListener("wheel", e => e.stopPropagation(), { passive: true });
  el.addEventListener("dblclick", e => e.stopPropagation());
  el.addEventListener("contextmenu", e => e.preventDefault());

  return { render, dispose() { renderer.dispose(); el.remove(); } };
}

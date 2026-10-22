import { EventDispatcher, Vector2, Vector3, Quaternion } from 'three';

// Free tumble controls for an orthographic camera: left drag rotates the camera about the pivot (target) with no
// limit on the angle (horizontal movement about the screen vertical axis, vertical movement about the screen
// horizontal axis), middle or right drag pans in the screen plane, the wheel zooms about the cursor.
// The pivot is set with setTarget(point, keepView) (keepView: the view does not jump).

const _change = { type: 'change' };

class TumbleControls extends EventDispatcher {
  constructor(camera, dom) {
    super();
    this.camera = camera;
    this.dom = dom;
    this.target = new Vector3();
    this.enabled = true;
    this.rotateSpeed = 0.009;      // rad per pixel
    this.zoomSpeed = 1.1;
    this.enableDamping = false;
    this.screenSpacePanning = true;
    this.mouseButtons = {};
    this._state = null;
    this._last = new Vector2();
    this._onDown = e => this._pointerDown(e);
    this._onMove = e => this._pointerMove(e);
    this._onUp = e => this._pointerUp(e);
    this._onWheel = e => this._wheel(e);
    dom.addEventListener('pointerdown', this._onDown);
    dom.addEventListener('wheel', this._onWheel, { passive: false });
    dom.addEventListener('contextmenu', e => e.preventDefault());
    dom.style.touchAction = 'none';
  }

  dispose() {
    this.dom.removeEventListener('pointerdown', this._onDown);
    this.dom.removeEventListener('wheel', this._onWheel);
  }

  update() { this.camera.lookAt(this.target); return true; }

  /** World units per pixel at the current zoom. */
  unitsPerPixel() {
    const c = this.camera, r = this.dom.getBoundingClientRect();
    return (c.right - c.left) / c.zoom / (r.width || 1);
  }

  /** Sets the pivot. keepView: the camera is moved by the same vector so the picture does not change. */
  setTarget(p, keepView) {
    const d = p.clone().sub(this.target);
    this.target.copy(p);
    if (keepView) {
      // only the component along the view direction changes the picture of an orthographic camera: none
      this.camera.position.add(d);
    }
    this.camera.lookAt(this.target);
    this.dispatchEvent(_change);
  }

  _pointerDown(e) {
    if (!this.enabled) return;
    if (e.button === 1) e.preventDefault();          // no browser autoscroll on the middle button
    this._state = e.button === 0 && !e.shiftKey ? 'rotate' : 'pan';
    this._last.set(e.clientX, e.clientY);
    this.dom.setPointerCapture(e.pointerId);
    this.dom.addEventListener('pointermove', this._onMove);
    this.dom.addEventListener('pointerup', this._onUp);
  }

  _pointerUp(e) {
    this._state = null;
    try { this.dom.releasePointerCapture(e.pointerId); } catch (err) { /* released */ }
    this.dom.removeEventListener('pointermove', this._onMove);
    this.dom.removeEventListener('pointerup', this._onUp);
  }

  _pointerMove(e) {
    if (!this._state) return;
    const dx = e.clientX - this._last.x, dy = e.clientY - this._last.y;
    this._last.set(e.clientX, e.clientY);
    if (!dx && !dy) return;
    if (this._state === 'rotate') this._rotate(dx, dy); else this._pan(dx, dy);
    this.dispatchEvent(_change);
  }

  _rotate(dx, dy) {
    const cam = this.camera;
    // screen axes in world space
    const right = new Vector3(1, 0, 0).applyQuaternion(cam.quaternion);
    const up = new Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
    const q = new Quaternion().setFromAxisAngle(up, -dx * this.rotateSpeed)
      .multiply(new Quaternion().setFromAxisAngle(right, -dy * this.rotateSpeed));
    const off = cam.position.clone().sub(this.target).applyQuaternion(q);
    cam.position.copy(this.target).add(off);
    cam.up.applyQuaternion(q);
    cam.lookAt(this.target);
  }

  _pan(dx, dy) {
    const cam = this.camera, k = this.unitsPerPixel();
    const right = new Vector3(1, 0, 0).applyQuaternion(cam.quaternion).multiplyScalar(-dx * k);
    const up = new Vector3(0, 1, 0).applyQuaternion(cam.quaternion).multiplyScalar(dy * k);
    const d = right.add(up);
    cam.position.add(d);
    this.target.add(d);
  }

  _wheel(e) {
    if (!this.enabled) return;
    e.preventDefault();
    const cam = this.camera, r = this.dom.getBoundingClientRect();
    const f = e.deltaY < 0 ? this.zoomSpeed : 1 / this.zoomSpeed;
    // zoom about the cursor: the world point under the cursor stays under it
    const nx = ((e.clientX - r.left) / r.width) * 2 - 1, ny = -((e.clientY - r.top) / r.height) * 2 + 1;
    const before = new Vector3(nx, ny, 0).unproject(cam);
    cam.zoom = Math.min(1e4, Math.max(1e-4, cam.zoom * f));
    cam.updateProjectionMatrix();
    const after = new Vector3(nx, ny, 0).unproject(cam);
    const d = before.sub(after);
    // only the in-plane part moves the picture
    const view = cam.getWorldDirection(new Vector3());
    d.sub(view.multiplyScalar(d.dot(view)));
    cam.position.add(d);
    this.target.add(d);
    this.dispatchEvent(_change);
  }
}

export { TumbleControls };

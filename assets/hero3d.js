// Hero scene: scattered spreadsheet cells assemble into one clean sheet.
// Duplicates shrink away, flagged cells glow, the cursor pushes cells and they spring back.
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const COLS = 14;
const ROWS = 9;
const DUPES = 16;
const CELL_W = 1.0;
const CELL_H = 0.46;
const GAP_X = 0.1;
const GAP_Y = 0.1;
const FLAGGED = new Set(['3:4', '6:9', '7:2']); // "row:col" cells that get flagged for review

const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const clamp01 = (v) => Math.min(1, Math.max(0, v));

export function initHero(canvas, { reduced = false } = {}) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  } catch {
    return null; // no WebGL: the hero keeps its plain background
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  camera.position.set(0, 0, 22);

  scene.add(new THREE.HemisphereLight(0xdbe4f0, 0x0b1220, 1.1));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(6, 9, 12);
  scene.add(key);
  const glow = new THREE.PointLight(0xfacc15, 0, 9, 1.6);
  glow.position.set(0, 0, 2.5);
  scene.add(glow);

  const group = new THREE.Group();
  scene.add(group);

  const geo = new RoundedBoxGeometry(CELL_W, CELL_H, 0.14, 3, 0.06);
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0.12 });
  const N = COLS * ROWS + DUPES;
  const mesh = new THREE.InstancedMesh(geo, mat, N);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  group.add(mesh);

  const cHeader = new THREE.Color('#cbd5e1');
  const cBody = new THREE.Color('#22304f');
  const cBodyAlt = new THREE.Color('#2a3a5e');
  const cFlag = new THREE.Color('#facc15');
  const cDupe = new THREE.Color('#475569');

  const cells = [];
  const rand = (a, b) => a + Math.random() * (b - a);
  const gridX = (c) => (c - (COLS - 1) / 2) * (CELL_W + GAP_X);
  const gridY = (r) => ((ROWS - 1) / 2 - r) * (CELL_H + GAP_Y);

  for (let i = 0; i < N; i++) {
    const isDupe = i >= COLS * ROWS;
    let r, c;
    if (isDupe) {
      r = 1 + Math.floor(Math.random() * (ROWS - 1));
      c = Math.floor(Math.random() * COLS);
    } else {
      r = Math.floor(i / COLS);
      c = i % COLS;
    }
    const chaosPos = new THREE.Vector3(rand(-13, 13), rand(-8, 8), rand(-9, 5));
    const chaosQuat = new THREE.Quaternion().setFromEuler(new THREE.Euler(rand(-Math.PI, Math.PI), rand(-Math.PI, Math.PI), rand(-Math.PI, Math.PI)));
    const orderPos = new THREE.Vector3(gridX(c), gridY(r), isDupe ? 0.02 : 0);
    const flagged = !isDupe && FLAGGED.has(`${r}:${c}`);
    const color = isDupe ? cDupe : r === 0 ? cHeader : flagged ? cFlag : (r % 2 ? cBody : cBodyAlt);
    mesh.setColorAt(i, color);
    cells.push({ r, c, isDupe, flagged, chaosPos, chaosQuat, orderPos, push: 0, delay: (c / COLS) * 0.9 + Math.random() * 0.12 });
  }
  mesh.instanceColor.needsUpdate = true;

  const dummy = new THREE.Object3D();
  const identity = new THREE.Quaternion();
  const tmpQ = new THREE.Quaternion();

  // Pointer, projected onto the sheet's plane in the group's local space
  const pointer = new THREE.Vector2(0, 0);
  const pointerLocal = new THREE.Vector3(999, 999, 0);
  const smoothTilt = new THREE.Vector2(0, 0);
  const raycaster = new THREE.Raycaster();
  const plane = new THREE.Plane();
  const planeNormal = new THREE.Vector3();
  const hit = new THREE.Vector3();
  let pointerActive = false;

  // Assembly progress: 0 = chaos, 1 = clean sheet
  let progress = reduced ? 1 : 0;
  let target = 1;
  let startAt = performance.now() + 250;

  function layout() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    const visH = 2 * camera.position.z * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const visW = visH * camera.aspect;
    const sheetW = COLS * (CELL_W + GAP_X);
    const wide = camera.aspect > 1.05;
    const fit = wide ? (visW * 0.46) / sheetW : (visW * 0.95) / sheetW;
    group.scale.setScalar(Math.min(fit, 1.15));
    group.position.set(wide ? visW * 0.24 : 0, wide ? -visH * 0.02 : visH * 0.2, 0);
    group.userData.baseRot = wide ? { x: -0.42, y: -0.52, z: -0.05 } : { x: -0.5, y: -0.3, z: -0.04 };
  }

  function updatePointerLocal() {
    if (!pointerActive) { pointerLocal.set(999, 999, 0); return; }
    raycaster.setFromCamera(pointer, camera);
    group.updateMatrixWorld();
    planeNormal.set(0, 0, 1).applyQuaternion(group.quaternion);
    plane.setFromNormalAndCoplanarPoint(planeNormal, group.position);
    if (raycaster.ray.intersectPlane(plane, hit)) {
      glow.position.copy(hit).addScaledVector(planeNormal, 1.4);
      pointerLocal.copy(group.worldToLocal(hit.clone()));
    }
  }

  function frame(now) {
    const t = now / 1000;
    if (!reduced) {
      const k = clamp01((now - startAt) / 3000);
      const goal = target === 1 ? easeInOut(k) : target;
      progress += (goal - progress) * (target === 1 ? 0.12 : 0.2);
    }

    const base = group.userData.baseRot || { x: -0.42, y: -0.52, z: 0 };
    smoothTilt.lerp(pointerActive ? pointer : new THREE.Vector2(0, 0), 0.05);
    group.rotation.set(base.x + smoothTilt.y * 0.1, base.y + smoothTilt.x * 0.16, base.z);

    updatePointerLocal();
    glow.intensity += ((pointerActive && !reduced ? 26 : 0) - glow.intensity) * 0.08;

    for (let i = 0; i < cells.length; i++) {
      const cell = cells[i];
      const e = easeInOut(clamp01((progress * 1.9 - cell.delay) / 0.9));
      dummy.position.lerpVectors(cell.chaosPos, cell.orderPos, e);
      tmpQ.copy(cell.chaosQuat).slerp(identity, e);
      dummy.quaternion.copy(tmpQ);

      let scale = 1;
      if (cell.isDupe) scale = 1 - clamp01((e - 0.55) / 0.4); // duplicates are removed
      if (!reduced) {
        dummy.position.z += Math.sin(t * 0.9 + cell.c * 0.45 + cell.r * 0.35) * 0.07 * e;
        const dx = cell.orderPos.x - pointerLocal.x;
        const dy = cell.orderPos.y - pointerLocal.y;
        const d = Math.sqrt(dx * dx + dy * dy);
        const want = d < 2.4 ? Math.pow(1 - d / 2.4, 2) * 1.6 * e : 0;
        cell.push += (want - cell.push) * 0.14;
        dummy.position.z += cell.push;
        dummy.rotation.setFromQuaternion(dummy.quaternion);
        dummy.rotation.x += cell.push * dy * 0.12;
        dummy.rotation.y -= cell.push * dx * 0.12;
      }
      if (cell.flagged) {
        const pulse = 1 + Math.sin(t * 2.4) * 0.04 * e;
        dummy.scale.set(pulse, pulse, pulse);
      } else {
        dummy.scale.setScalar(Math.max(scale, 0.0001));
      }
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
    renderer.render(scene, camera);
  }

  let running = false;
  let visible = true;
  let raf = 0;
  const loop = (now) => { frame(now); raf = requestAnimationFrame(loop); };
  const start = () => { if (!running && visible && !document.hidden && !reduced) { running = true; raf = requestAnimationFrame(loop); } };
  const stop = () => { running = false; cancelAnimationFrame(raf); };

  const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; visible ? start() : stop(); });
  io.observe(canvas);
  document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));

  const ro = new ResizeObserver(() => { layout(); if (reduced) frame(performance.now()); });
  ro.observe(canvas);

  if (!reduced) {
    const host = canvas.closest('[data-hero]') || canvas;
    host.addEventListener('pointermove', (ev) => {
      const rect = canvas.getBoundingClientRect();
      pointer.set(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
      pointerActive = ev.pointerType === 'mouse';
    });
    host.addEventListener('pointerleave', () => { pointerActive = false; });
    // Clicking empty hero space scatters the sheet, then it cleans itself again
    host.addEventListener('pointerdown', (ev) => {
      if (ev.target.closest('a, button')) return;
      target = 0.08;
      setTimeout(() => { target = 1; startAt = performance.now() - 600; }, 420);
    });
  }

  layout();
  frame(performance.now());
  start();
  return { destroy() { stop(); io.disconnect(); ro.disconnect(); renderer.dispose(); geo.dispose(); mat.dispose(); } };
}

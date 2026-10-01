// The trading room: desk, chair, monitors, LONG/SHORT buttons, a window onto a penthouse terrace, the
// net-worth milestone props, and the event effects (confetti, sparkles, alarm, dizzy stars, blackout).
// Desk/monitor/lighting layout follows "The Degeneret Fly" src/studio.ts (MIT, Robillionair OÜ).
import * as T from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { makeFly } from './fly.js';

const HOME = { pos: new T.Vector3(5.2, 3.55, 6.4), target: new T.Vector3(.05, 1.8, -.3) };
// Broadcast camera shots for events; the studio cuts to one and eases back to the viewer's framing.
const SHOTS = {
  face: { pos: new T.Vector3(-2.8, 3.2, -1.2), target: new T.Vector3(.62, 1.9, 1.0) },
  desk: { pos: new T.Vector3(3.3, 2.75, 2.6), target: new T.Vector3(.7, 1.55, .2) },
  wide: { pos: new T.Vector3(6.6, 4.6, 3.4), target: new T.Vector3(-1.3, 1.7, -.6) },
  window: { pos: new T.Vector3(1.6, 2.9, 4.4), target: new T.Vector3(-6.5, 2.0, -.6) },
};
const SHOT_FOR = { gold_chain: 'face', luxury_sedan: 'window', yacht: 'window', helicopter: 'window' };
const ease = u => u < .5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
const FONT = '"Pretendard Variable", Pretendard, "Malgun Gothic", sans-serif';

export function canvasTexture(w, h) {
  const canvas = document.createElement('canvas'); canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d'); const tex = new T.CanvasTexture(canvas);
  tex.colorSpace = T.SRGBColorSpace; tex.anisotropy = 4;
  return { canvas, ctx, tex };
}

function textSprite(text, color, bg) {
  const { ctx, tex } = canvasTexture(512, 160);
  ctx.fillStyle = bg; ctx.beginPath(); ctx.roundRect(8, 8, 496, 144, 28); ctx.fill();
  ctx.lineWidth = 8; ctx.strokeStyle = color; ctx.stroke();
  ctx.fillStyle = color; ctx.font = `800 92px ${FONT}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(text, 256, 86);
  const s = new T.Sprite(new T.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
  s.scale.set(1.05, .33, 1); s.renderOrder = 10; return s;
}

function skyline() {
  const { ctx, tex } = canvasTexture(2048, 1024);
  const W = 2048, H = 1024, horizon = H * .72;
  const sky = ctx.createLinearGradient(0, 0, 0, horizon);
  sky.addColorStop(0, '#070a1c'); sky.addColorStop(.6, '#131a3a'); sky.addColorStop(1, '#2a2350');
  ctx.fillStyle = sky; ctx.fillRect(0, 0, W, horizon);
  let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 260; i++) { ctx.fillStyle = `rgba(255,255,255,${.25 + rnd() * .6})`; ctx.fillRect(rnd() * W, rnd() * horizon * .7, 2, 2); }
  ctx.fillStyle = '#f4efd8'; ctx.beginPath(); ctx.arc(W * .78, H * .16, 46, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#070a1c'; ctx.beginPath(); ctx.arc(W * .78 + 18, H * .16 - 10, 42, 0, Math.PI * 2); ctx.fill();
  for (let layer = 0; layer < 2; layer++) {
    let x = 0;
    while (x < W) {
      const w = 40 + rnd() * 110, h = (layer ? 90 : 160) + rnd() * (layer ? 180 : 330);
      ctx.fillStyle = layer ? '#10142a' : '#1a1f3d'; ctx.fillRect(x, horizon - h, w, h);
      for (let wy = horizon - h + 12; wy < horizon - 8; wy += 16) for (let wx = x + 8; wx < x + w - 8; wx += 14) {
        if (rnd() < (layer ? .45 : .3)) { ctx.fillStyle = rnd() < .8 ? '#f6d27a' : '#9fd3ff'; ctx.globalAlpha = .55 + rnd() * .45; ctx.fillRect(wx, wy, 6, 8); ctx.globalAlpha = 1; }
      }
      x += w + 4 + rnd() * 20;
    }
  }
  const sea = ctx.createLinearGradient(0, horizon, 0, H);
  sea.addColorStop(0, '#16213f'); sea.addColorStop(1, '#070b18'); ctx.fillStyle = sea; ctx.fillRect(0, horizon, W, H - horizon);
  for (let i = 0; i < 180; i++) { ctx.fillStyle = `rgba(246,210,122,${rnd() * .35})`; ctx.fillRect(rnd() * W, horizon + rnd() * (H - horizon), 30 + rnd() * 80, 2); }
  return tex;
}

export class Studio {
  // lite: phones and small screens — lower pixel ratio, smaller shadow maps, a slower face cam.
  constructor(canvas, faceCanvas, { lite = false } = {}) {
    this.canvas = canvas; this.clock = 0; this.effects = []; this.shakeAmp = 0; this.lastShake = new T.Vector3();
    this.lite = lite; this.faceStep = lite ? 1 / 12 : 1 / 24;
    const r = this.renderer = new T.WebGLRenderer({ canvas, antialias: true });
    r.setPixelRatio(Math.min(devicePixelRatio, lite ? 1.25 : 1.75)); r.shadowMap.enabled = true; r.shadowMap.type = T.PCFSoftShadowMap;
    r.toneMapping = T.ACESFilmicToneMapping; r.toneMappingExposure = 1.45;
    const scene = this.scene = new T.Scene();
    scene.background = new T.Color(0x14171b); scene.fog = new T.Fog(0x14171b, 18, 40);
    this.camera = new T.PerspectiveCamera(35, 16 / 9, .1, 150); this.camera.position.copy(HOME.pos);
    const c = this.controls = new OrbitControls(this.camera, canvas);
    c.target.copy(HOME.target); c.enableDamping = true; c.maxPolarAngle = Math.PI * .49; c.minDistance = 1.5; c.maxDistance = 17;
    this.cutState = null; this.lastUser = -1e9;
    c.addEventListener('start', () => { this.lastUser = this.clock; this.cutState = null; });

    // Lighting (same rig as the reference desk) plus an alarm light and a blackout spotlight.
    this.hemi = new T.HemisphereLight(0xcbe7ff, 0x5c4934, 2.8); scene.add(this.hemi);
    const spot = (color, power, pos) => {
      const l = new T.SpotLight(color, power, 25, Math.PI / 4, .5, 1.5); l.position.set(...pos); l.castShadow = true;
      const m = lite ? 1024 : 2048; l.shadow.mapSize.set(m, m); l.shadow.bias = -.00015; scene.add(l); return l;
    };
    const fill = new T.DirectionalLight(0xdfe8ff, 1.1); fill.position.set(6, 5, 8); scene.add(fill);
    this.lights = [this.hemi, spot(0xffe1b8, 130, [-3, 7, 4]), spot(0x92b6ff, 75, [5, 5, -3]), spot(0xf2a1d0, 30, [-5, 3, -2]), fill];
    this.base = this.lights.map(l => l.intensity);
    this.alarm = new T.PointLight(0xff2a2a, 0, 14); this.alarm.position.set(.6, 3.6, .9); scene.add(this.alarm); this.alarmT = 0;
    this.blackout = new T.SpotLight(0xfff1d6, 0, 12, Math.PI / 10, .6, 1.2); this.blackout.position.set(.65, 6.5, 2.2);
    this.blackout.target.position.set(.65, 1.4, .9); scene.add(this.blackout, this.blackout.target); this.dark = 0; this.darkTarget = 0;

    // Materials.
    const wood = new T.MeshStandardMaterial({ color: 0x684a35, roughness: .55, metalness: .06 });
    wood.onBeforeCompile = s => { s.fragmentShader = s.fragmentShader.replace('#include <color_fragment>', '#include <color_fragment>\n diffuseColor.rgb *= .92+.08*sin(vViewPosition.x*85.+sin(vViewPosition.z*20.)*3.);'); };
    const metal = this.metal = new T.MeshStandardMaterial({ color: 0x171c20, roughness: .34, metalness: .72 });
    const gold = this.gold = new T.MeshStandardMaterial({ color: 0xe5ad47, metalness: 1, roughness: .21 });
    const box = (w, h, d, mat, x, y, z, parent = scene) => {
      const m = new T.Mesh(new T.BoxGeometry(w, h, d), mat); m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; parent.add(m); return m;
    };
    this.box = box;

    // Room shell: floor, back wall and a left wall with a big window onto the terrace.
    box(40, .1, 40, new T.MeshStandardMaterial({ color: 0x1c2026, roughness: .94 }), 0, -.12, 0);
    const wallMat = new T.MeshStandardMaterial({ color: 0x1d2230, roughness: .9 });
    box(14, 6, .2, wallMat, 0, 2.9, -2.8);
    const wx = -3.55;
    box(.2, 1.0, 6.4, wallMat, wx, .5, .3); box(.2, 2.3, 6.4, wallMat, wx, 4.75, .3);
    box(.2, 2.6, .8, wallMat, wx, 2.3, -2.5); box(.2, 2.6, 1.8, wallMat, wx, 2.3, 2.6);
    const frame = new T.MeshStandardMaterial({ color: 0x0d1016, roughness: .4, metalness: .6 });
    for (const [h, y] of [[.08, 1.0], [.08, 3.6]]) box(.26, h, 3.8, frame, wx, y, -.2);
    for (const z of [-2.1, -.2, 1.7]) box(.26, 2.6, .08, frame, wx, 2.3, z);
    const glass = new T.Mesh(new T.PlaneGeometry(3.8, 2.6), new T.MeshBasicMaterial({ color: 0x8fb4ff, transparent: true, opacity: .05, depthWrite: false }));
    glass.position.set(wx, 2.3, -.2); glass.rotation.y = Math.PI / 2; scene.add(glass);
    const backdrop = new T.Mesh(new T.PlaneGeometry(70, 30), new T.MeshBasicMaterial({ map: skyline(), fog: false, toneMapped: false }));
    backdrop.position.set(-26, 5.2, -2); backdrop.rotation.y = Math.PI / 2; scene.add(backdrop);
    const deck = box(6.2, .14, 6.0, new T.MeshStandardMaterial({ color: 0x2a303b, roughness: .8 }), -6.75, .93, -.3);
    deck.receiveShadow = true;
    for (let z = -3.2; z <= 2.6; z += .58) box(.05, .6, .05, frame, -9.8, 1.3, z);
    box(.06, .05, 5.9, frame, -9.8, 1.6, -.3);
    const terraceLight = new T.PointLight(0xffc98a, 6, 9); terraceLight.position.set(-6.4, 3.2, -.2); scene.add(terraceLight);

    // Desk.
    box(5.0, .14, 1.85, wood, .35, 1.29, -.3);
    for (const x of [-1.95, 2.65]) for (const z of [-1.02, .42]) box(.07, 1.26, .07, metal, x, .58, z);
    box(.45, .75, .72, metal, 2.3, .32, -.5);
    for (let i = 0; i < 5; i++) box(.012, .015, .35, new T.MeshBasicMaterial({ color: 0xbca4ff }), 2.08, .5 + i * .07, -.48);

    // Chair: static base plus a swivel group that carries the seat, the back and the fly.
    const chairMat = this.chairMat = new T.MeshStandardMaterial({ color: 0x242a35, roughness: .48, metalness: .25 });
    box(.10, .64, .10, metal, .65, .43, 1.04);
    for (let i = 0; i < 5; i++) {
      const a = i * Math.PI * 2 / 5; const spoke = box(.055, .055, .55, metal, .65 + Math.sin(a) * .24, .12, 1.04 + Math.cos(a) * .24); spoke.rotation.y = a;
      const wheel = new T.Mesh(new T.CylinderGeometry(.075, .075, .06, 14), metal); wheel.rotation.z = Math.PI / 2;
      wheel.position.set(.65 + Math.sin(a) * .48, .075, 1.04 + Math.cos(a) * .48); scene.add(wheel);
    }
    const swivel = this.swivel = new T.Group(); swivel.position.set(.65, .82, 1.04); scene.add(swivel);
    box(.99, .14, .82, chairMat, 0, 0, 0, swivel); this.chairBack = box(.86, 1.0, .14, chairMat, 0, .56, .44, swivel);
    for (const side of [-1, 1]) { box(.06, .39, .06, metal, side * .5, .2, .03, swivel); box(.12, .07, .51, chairMat, side * .5, .4, .03, swivel); }
    this.chairTrim = box(.9, .05, .16, gold, 0, 1.07, .44, swivel); this.chairTrim.visible = false;

    // Fly.
    this.fly = makeFly();
    this.fly.group.position.set(0, -.57, .04); this.fly.group.rotation.y = Math.PI; this.fly.group.scale.setScalar(.92);
    swivel.add(this.fly.group);

    // Monitors with canvas textures: main (always), second and third (room milestones).
    this.screens = {};
    const monitor = (name, w, h, px, py, pz, rotY, cw, ch) => {
      const g = new T.Group(); g.position.set(px, py, pz); g.rotation.y = rotY; scene.add(g);
      box(w + .11, h + .11, .10, metal, 0, 0, 0, g); box(.12, .42, .10, metal, 0, -h / 2 - .2, -.02, g); box(.62, .055, .34, metal, 0, -h / 2 - .41, .01, g);
      const s = canvasTexture(cw, ch);
      const display = new T.Mesh(new T.PlaneGeometry(w, h), new T.MeshBasicMaterial({ map: s.tex, toneMapped: false }));
      display.position.z = .056; g.add(display);
      this.screens[name] = { ...s, group: g, w: cw, h: ch };
      return g;
    };
    monitor('main', 2.29, 1.37, .65, 2.25, -.74, 0, 1280, 768);
    this.items = {};
    this.items.dual_monitor = monitor('second', 1.7, 1.02, -1.55, 2.08, -.62, .42, 1024, 614);
    this.items.triple_monitor_leather_chair = monitor('third', 1.7, 1.02, 2.62, 2.08, -.58, -.42, 1024, 614);
    const monitorLight = new T.PointLight(0xafbfff, 3, 3); monitorLight.position.set(.4, 2, -.2); scene.add(monitorLight); this.monitorLight = monitorLight;

    // Keyboard, mouse, mat, cup and a desk lamp.
    const keyboard = box(1.15, .05, .4, metal, .65, 1.4, .15);
    const keyMat = new T.MeshStandardMaterial({ color: 0x4a5058, roughness: .5 });
    for (let rr = 0; rr < 4; rr++) for (let cc = 0; cc < 14; cc++) box(.056, .027, .060, keyMat, .15 + cc * .072, 1.441, .018 + rr * .08);
    void keyboard;
    box(2.2, .008, .7, new T.MeshStandardMaterial({ color: 0x202530, roughness: .9 }), .75, 1.367, .14);
    const mouse = new T.Mesh(new T.SphereGeometry(.12, 20, 12), metal); mouse.scale.set(.7, .4, 1.25); mouse.position.set(1.95, 1.43, .12); scene.add(mouse);
    const cup = new T.Mesh(new T.CylinderGeometry(.105, .08, .20, 24), new T.MeshStandardMaterial({ color: 0xc7b395, roughness: .7 })); cup.position.set(2.35, 1.47, .1); scene.add(cup);
    box(.035, .85, .035, metal, -2.0, 1.78, -.95); box(.42, .04, .18, metal, -1.83, 2.22, -.95);
    const deskLight = new T.PointLight(0xffcc80, 3, 2); deskLight.position.set(-1.85, 2.15, -.88); scene.add(deskLight);

    // The two big arcade buttons the fly slams: 롱 (green, right of the keyboard) and 숏 (red, left).
    this.buttons = {};
    const button = (name, color, x, label) => {
      const g = new T.Group(); g.position.set(x, 1.36, .34); scene.add(g);
      const base = new T.Mesh(new T.CylinderGeometry(.19, .21, .07, 32), metal); base.position.y = .035; base.castShadow = true; g.add(base);
      const mat = new T.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: .35, roughness: .3, metalness: .1 });
      const cap = new T.Mesh(new T.CylinderGeometry(.14, .15, .09, 32), mat); cap.position.y = .11; cap.castShadow = true; g.add(cap);
      const tag = canvasTexture(256, 128); tag.ctx.fillStyle = '#0c0f15'; tag.ctx.fillRect(0, 0, 256, 128);
      tag.ctx.fillStyle = `#${new T.Color(color).getHexString()}`; tag.ctx.font = `800 84px ${FONT}`; tag.ctx.textAlign = 'center'; tag.ctx.textBaseline = 'middle'; tag.ctx.fillText(label, 128, 70);
      const plate = new T.Mesh(new T.PlaneGeometry(.34, .17), new T.MeshBasicMaterial({ map: tag.tex, toneMapped: false }));
      plate.rotation.x = -Math.PI / 2; plate.position.set(0, .01, .3); g.add(plate);
      const glow = new T.PointLight(color, 0, 2.2); glow.position.y = .4; g.add(glow);
      this.buttons[name] = { cap, mat, glow, t: 9 };
    };
    button('long', 0x2fd18a, 1.45, '롱');
    button('short', 0xff4d5e, -.15, '숏');

    this.buildMilestones();
    this.buildEffects();

    // Face camera for the "FLY CAM" inset (24 fps).
    this.faceCamera = new T.PerspectiveCamera(46, 4 / 3, .05, 60);
    this.faceCamera.position.set(.62, 2.3, -.6); this.faceCamera.lookAt(.65, 2.0, 1.0);
    if (faceCanvas) {
      this.faceRenderer = new T.WebGLRenderer({ canvas: faceCanvas, antialias: true }); this.faceRenderer.setPixelRatio(1);
      this.faceRenderer.toneMapping = T.ACESFilmicToneMapping; this.faceRenderer.toneMappingExposure = 1.6; this.lastFace = 0;
      new ResizeObserver(() => { const w = faceCanvas.clientWidth, h = faceCanvas.clientHeight; if (!w || !h) return; this.faceRenderer.setSize(w, h, false); this.faceCamera.aspect = w / h; this.faceCamera.updateProjectionMatrix(); }).observe(faceCanvas.parentElement);
    }
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement); this.resize();
  }

  buildMilestones() {
    const { scene, box, gold, metal } = this;
    const own = color => new T.MeshStandardMaterial({ color, roughness: .35, metalness: .4 });
    const group = (x, y, z) => { const g = new T.Group(); g.position.set(x, y, z); scene.add(g); return g; };
    // 1,200 — coffee machine on the left of the desk.
    const cm = group(-1.9, 1.36, .15);
    box(.36, .46, .32, own(0x2b2f36), 0, .23, 0, cm); box(.4, .06, .36, own(0x9aa3ad), 0, .49, 0, cm);
    const spout = new T.Mesh(new T.CylinderGeometry(.05, .05, .1, 16), own(0x9aa3ad)); spout.position.set(0, .31, .2); cm.add(spout);
    const espresso = new T.Mesh(new T.CylinderGeometry(.05, .04, .07, 16), own(0xf2ece0)); espresso.position.set(0, .04, .22); cm.add(espresso);
    const led = new T.Mesh(new T.SphereGeometry(.018, 8, 8), new T.MeshBasicMaterial({ color: 0xff5050 })); led.position.set(.12, .4, .165); cm.add(led);
    this.items.coffee_machine = cm;
    // 2,000 — the gold chain on the fly.
    this.items.gold_chain = this.fly.chain;
    // 5,000 — a luxury sedan parked on the terrace outside the window.
    const car = group(-6.6, 1.0, -.7); car.rotation.y = .5; car.scale.setScalar(1.25);
    const paint = new T.MeshPhysicalMaterial({ color: 0x0f0f14, metalness: .8, roughness: .22, clearcoat: 1, clearcoatRoughness: .05 });
    box(2.6, .42, 1.1, paint, 0, .42, 0, car); box(1.45, .36, .98, new T.MeshPhysicalMaterial({ color: 0x0a0d14, metalness: .3, roughness: .05, clearcoat: 1 }), -.1, .8, 0, car);
    for (const x of [-.85, .85]) for (const z of [-.56, .56]) { const w = new T.Mesh(new T.CylinderGeometry(.22, .22, .16, 20), metal); w.rotation.x = Math.PI / 2; w.position.set(x, .22, z); car.add(w); }
    for (const z of [-.38, .38]) { const l = new T.Mesh(new T.BoxGeometry(.04, .08, .22), new T.MeshBasicMaterial({ color: 0xfff4d0 })); l.position.set(1.31, .5, z); car.add(l); const t = new T.Mesh(new T.BoxGeometry(.04, .07, .24), new T.MeshBasicMaterial({ color: 0xff2a2a })); t.position.set(-1.31, .5, z); car.add(t); }
    box(.03, .08, .5, gold, 1.31, .36, 0, car);
    this.items.luxury_sedan = car;
    // 10,000 — a yacht out at sea.
    const yacht = group(-17, .35, -5.5); yacht.scale.setScalar(2.2); yacht.rotation.y = .3;
    const hullShape = new T.Shape(); hullShape.moveTo(-1.6, 0); hullShape.lineTo(1.3, 0); hullShape.quadraticCurveTo(1.9, .1, 2.1, .5); hullShape.lineTo(-1.6, .5); hullShape.lineTo(-1.6, 0);
    const hull = new T.Mesh(new T.ExtrudeGeometry(hullShape, { depth: .9, bevelEnabled: false }), own(0xf3f4f6)); hull.position.z = -.45; yacht.add(hull);
    box(1.8, .32, .7, own(0xf3f4f6), -.3, .66, 0, yacht); box(1.0, .26, .55, own(0x1a2233), -.4, .95, 0, yacht);
    const mast = new T.Mesh(new T.CylinderGeometry(.02, .02, 1.4, 8), own(0xdadde2)); mast.position.set(.2, 1.5, 0); yacht.add(mast);
    const yl = new T.PointLight(0xfff0c8, 2, 6); yl.position.set(0, 1.2, 0); yacht.add(yl);
    this.items.yacht = yacht;
    // 20,000 — a pile of gold bars on the floor right of the desk.
    const bars = group(3.25, 0, 1.0);
    let n = 0;
    for (let layer = 0; layer < 4; layer++) for (let i = 0; i < 4 - layer; i++) {
      const b = box(.36, .13, .17, gold, (i - (3 - layer) / 2) * .38, .065 + layer * .13, 0, bars); b.rotation.y = (n++ % 2) * .05;
    }
    this.items.gold_bars = bars;
    // 50,000 — a helicopter hovering over the terrace.
    const heli = group(-7.2, 3.7, 1.2); heli.rotation.y = -.6; heli.scale.setScalar(1.3);
    const body = new T.Mesh(new T.SphereGeometry(.55, 24, 16), new T.MeshPhysicalMaterial({ color: 0xd9b24a, metalness: .9, roughness: .25, clearcoat: 1 })); body.scale.set(1.5, .9, .9); heli.add(body);
    const boom = new T.Mesh(new T.CylinderGeometry(.08, .12, 1.8, 10), own(0xd9b24a)); boom.rotation.z = Math.PI / 2; boom.position.set(-1.5, .1, 0); heli.add(boom);
    const rotor = new T.Group(); rotor.position.y = .62; heli.add(rotor);
    for (const a of [0, Math.PI / 2]) { const blade = new T.Mesh(new T.BoxGeometry(3.2, .02, .12), own(0x20242b)); blade.rotation.y = a; rotor.add(blade); }
    const tail = new T.Mesh(new T.BoxGeometry(.5, .02, .06), own(0x20242b)); tail.position.set(-2.35, .2, .1); tail.rotation.x = Math.PI / 2; heli.add(tail);
    for (const z of [-.35, .35]) box(1.4, .04, .05, metal, 0, -.62, z, heli);
    heli.userData.spin = [rotor, tail];
    this.items.helicopter = heli;
    for (const [name, obj] of Object.entries(this.items)) { obj.visible = false; obj.userData.item = name; }
    this.leather = new T.MeshStandardMaterial({ color: 0x6b3a22, roughness: .55, metalness: .15 });
  }

  buildEffects() {
    // Confetti for wins and unlocks.
    const N = 260; this.confettiN = N;
    this.confetti = new T.InstancedMesh(new T.PlaneGeometry(.07, .04), new T.MeshBasicMaterial({ side: T.DoubleSide, toneMapped: false }), N);
    this.confetti.frustumCulled = false; this.confetti.visible = false; this.scene.add(this.confetti);
    this.confettiState = Array.from({ length: N }, () => ({ p: new T.Vector3(), v: new T.Vector3(), r: new T.Euler(), w: new T.Vector3(), life: 0 }));
    const palette = [0xffd166, 0x2fd18a, 0x5ec8ff, 0xff7ab6, 0xffffff, 0xe5ad47];
    for (let i = 0; i < N; i++) this.confetti.setColorAt(i, new T.Color(palette[i % palette.length]));
    // Dizzy stars that orbit the head after a liquidation.
    const star = new T.Shape(); for (let i = 0; i < 10; i++) { const a = i / 10 * Math.PI * 2 - Math.PI / 2, r = i % 2 ? .05 : .12; if (i) star.lineTo(Math.cos(a) * r, Math.sin(a) * r); else star.moveTo(Math.cos(a) * r, Math.sin(a) * r); }
    this.stars = Array.from({ length: 3 }, () => { const m = new T.Mesh(new T.ShapeGeometry(star), new T.MeshBasicMaterial({ color: 0xffe066, side: T.DoubleSide, toneMapped: false })); m.visible = false; this.scene.add(m); return m; });
    this.dummy = new T.Object3D(); this.tmp = new T.Vector3();
  }

  resize() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight; if (!w || !h) return;
    this.renderer.setSize(w, h, false); this.camera.aspect = w / h;
    // Every shot is framed for the 16:9 stage. On a narrower stage (a phone in portrait) keep the
    // same horizontal field of view by widening the vertical one, so the desk is not cropped.
    const halfH = Math.tan(T.MathUtils.degToRad(35 / 2)) * (1.62 / Math.min(1.62, w / h));
    this.camera.fov = Math.min(64, T.MathUtils.radToDeg(2 * Math.atan(halfH)));
    this.camera.updateProjectionMatrix();
  }

  home() { this.cutState = null; this.camera.position.copy(HOME.pos); this.controls.target.copy(HOME.target); }
  // Cut to a named shot for `hold` seconds, then ease back. Skipped while the viewer is driving.
  // Face shots (dance, liquidation, bankruptcy) outrank item and desk shots while they are on air.
  cut(name, hold = 4) {
    const shot = SHOTS[name]; if (!shot || this.clock - this.lastUser < 20) return;
    const prio = name === 'face' ? 2 : 1, cur = this.cutState;
    if (cur && cur.prio > prio && cur.t < .75 + cur.hold) return;
    const home = cur ? cur.home : { pos: this.camera.position.clone().sub(this.lastShake), target: this.controls.target.clone() };
    this.cutState = { home, shot, hold, prio, t: 0, pos: this.camera.position.clone().sub(this.lastShake), target: this.controls.target.clone() };
  }
  react(g) { this.fly.react(g); }
  then(g) { this.fly.then(g); }

  // ---- event effects -------------------------------------------------------------------------------
  burstConfetti(center = new T.Vector3(.65, 3.6, .9), count = 220) {
    this.confetti.visible = true; let k = 0;
    for (const s of this.confettiState) {
      if (k++ >= count) break;
      s.p.set(center.x + (Math.random() - .5) * 2.2, center.y + Math.random() * 1.2, center.z + (Math.random() - .5) * 2.2);
      s.v.set((Math.random() - .5) * 1.4, 1.2 + Math.random() * 1.6, (Math.random() - .5) * 1.4);
      s.r.set(Math.random() * 6, Math.random() * 6, Math.random() * 6); s.w.set(Math.random() * 8, Math.random() * 8, Math.random() * 8);
      s.life = 3.2 + Math.random() * 1.2;
    }
  }
  pressButton(name) { const b = this.buttons[name]; if (b) b.t = 0; }
  alarmOn(seconds = 4) { this.alarmT = seconds; this.shakeAmp = .12; }
  shake(amount = .06) { this.shakeAmp = Math.max(this.shakeAmp, amount); }
  setBankrupt(on) { this.darkTarget = on ? 1 : 0; }
  setLeather(on) {
    const m = on ? this.leather : this.chairMat;
    this.swivel.children.forEach(ch => { if (ch.isMesh && ch.material !== this.metal && ch !== this.chairTrim) ch.material = m; });
    this.chairTrim.visible = on;
  }

  // Sync the room with the ledger's unlocked list. `animate` plays the unlock/repossess effects.
  setUnlocked(list, animate) {
    const want = new Set(list || []);
    for (const [name, obj] of Object.entries(this.items)) {
      const has = obj.visible && obj.userData.anim?.type !== 'out';
      if (want.has(name) && !has) {
        obj.visible = true; obj.userData.anim = null;
        obj.traverse(o => { if (o.isMesh && o.userData.origMat) { o.material.dispose(); o.material = o.userData.origMat; delete o.userData.origMat; } });
        if (name === 'triple_monitor_leather_chair') this.setLeather(true);
        if (animate) {
          obj.userData.anim = { type: 'in', t: 0 }; obj.scale.setScalar(.001); this.flashLabel(obj, '획득!', '#ffd166');
          this.burstConfetti(this.worldOf(obj).add(new T.Vector3(0, 1.2, 0)), 120); this.cut(SHOT_FOR[name] || 'wide', 3.2);
        }
      } else if (!want.has(name) && has) {
        if (animate) {
          // Blink on private material copies so shared materials (gold, chair) elsewhere stay untouched.
          obj.traverse(o => { if (o.isMesh && !o.userData.origMat) { o.userData.origMat = o.material; o.material = o.material.clone(); } });
          obj.userData.anim = { type: 'out', t: 0, scale: obj.scale.x || 1 }; this.flashLabel(obj, '압류', '#ff4d5e');
          this.cut(SHOT_FOR[name] || 'wide', 2.8);
        }
        else { obj.visible = false; if (name === 'triple_monitor_leather_chair') this.setLeather(false); }
      }
    }
  }
  worldOf(obj) { obj.updateWorldMatrix(true, false); return new T.Vector3().setFromMatrixPosition(obj.matrixWorld); }
  flashLabel(obj, text, color) {
    const s = textSprite(text, color, 'rgba(10,12,18,.85)'); const at = this.worldOf(obj);
    s.position.copy(at).add(new T.Vector3(0, obj === this.fly.chain ? 1.2 : 1.4, 0)); this.scene.add(s);
    this.effects.push({ obj: s, t: 0, life: 2.6 });
  }

  // ---- frame ---------------------------------------------------------------------------------------
  render(dt, mood) {
    this.clock += dt; const t = this.clock;
    this.camera.position.sub(this.lastShake);
    const s = this.cutState;
    if (s) {
      s.t += dt; const inT = .75, outT = 1.1, p = new T.Vector3(), g = new T.Vector3();
      if (s.t < inT) { const k = ease(s.t / inT); p.lerpVectors(s.pos, s.shot.pos, k); g.lerpVectors(s.target, s.shot.target, k); }
      else if (s.t < inT + s.hold) { const d = (s.t - inT) * .05; p.copy(s.shot.pos).add(new T.Vector3(Math.sin(d) * .25, 0, -Math.sin(d) * .12)); g.copy(s.shot.target); }
      else if (s.t < inT + s.hold + outT) { const k = ease((s.t - inT - s.hold) / outT); p.lerpVectors(s.shot.pos, s.home.pos, k); g.lerpVectors(s.shot.target, s.home.target, k); }
      else { p.copy(s.home.pos); g.copy(s.home.target); this.cutState = null; }
      this.camera.position.copy(p); this.controls.target.copy(g); this.camera.lookAt(g);
    } else this.controls.update();
    this.fly.animate(t, dt, mood);
    this.swivel.rotation.set(this.fly.pose.tip, this.fly.pose.swivel, 0);
    while (this.fly.impacts.length) { const side = this.fly.impacts.shift(); this.pressButton(side); this.shake(.035); }
    for (const b of Object.values(this.buttons)) {
      b.t += dt; const hit = Math.max(0, 1 - b.t / .9);
      b.cap.position.y = .11 - (b.t < .18 ? .04 : 0); b.mat.emissiveIntensity = .35 + hit * 3.2; b.glow.intensity = hit * 9;
    }
    // Items: unlock grow / repossess blink-and-shrink.
    for (const obj of Object.values(this.items)) {
      if (obj.userData.spin && obj.visible) { obj.userData.spin[0].rotation.y += dt * 22; obj.userData.spin[1].rotation.z += dt * 30; obj.position.y = 3.7 + Math.sin(t * 1.3) * .12; }
      const a = obj.userData.anim; if (!a) continue;
      a.t += dt;
      if (a.type === 'in') {
        const u = Math.min(1, a.t / .9), back = 1 + 2.2 * Math.pow(u - 1, 3) + 1.2 * Math.pow(u - 1, 2);
        obj.scale.setScalar(Math.max(.001, back)); if (u >= 1) { obj.scale.setScalar(1); obj.userData.anim = null; }
      } else {
        const blink = a.t < 1.4 && Math.floor(a.t * 8) % 2 === 0;
        obj.traverse(o => { if (o.isMesh && o.userData.origMat && o.material.emissive) o.material.emissive.setHex(blink ? 0xff2020 : 0x000000); });
        if (a.t > 1.4) obj.scale.setScalar(Math.max(.001, a.scale * (1 - (a.t - 1.4) / .7)));
        if (a.t > 2.1) {
          obj.visible = false; obj.scale.setScalar(1); obj.userData.anim = null;
          obj.traverse(o => { if (o.isMesh && o.userData.origMat) { o.material.dispose(); o.material = o.userData.origMat; delete o.userData.origMat; } });
          if (obj.userData.item === 'triple_monitor_leather_chair') this.setLeather(false);
        }
      }
    }
    // Floating labels.
    this.effects = this.effects.filter(e => {
      e.t += dt; e.obj.position.y += dt * .35; e.obj.material.opacity = Math.min(1, (e.life - e.t) / .6);
      if (e.t > e.life) { this.scene.remove(e.obj); e.obj.material.map.dispose(); e.obj.material.dispose(); return false; }
      return true;
    });
    // Confetti physics.
    if (this.confetti.visible) {
      let alive = 0;
      this.confettiState.forEach((s, i) => {
        if (s.life > 0) {
          s.life -= dt; s.v.y -= 2.6 * dt; s.v.multiplyScalar(1 - dt * .6); s.p.addScaledVector(s.v, dt);
          if (s.p.y < 0) { s.p.y = 0; s.v.set(0, 0, 0); }
          s.r.x += s.w.x * dt; s.r.y += s.w.y * dt; s.r.z += s.w.z * dt; alive++;
          this.dummy.position.copy(s.p); this.dummy.rotation.copy(s.r); this.dummy.scale.setScalar(Math.min(1, s.life * 2));
        } else this.dummy.scale.setScalar(0);
        this.dummy.updateMatrix(); this.confetti.setMatrixAt(i, this.dummy.matrix);
      });
      this.confetti.instanceMatrix.needsUpdate = true; if (!alive) this.confetti.visible = false;
    }
    // Dizzy stars around the head.
    const dz = this.fly.pose.dizzy;
    this.fly.head.getWorldPosition(this.tmp);
    this.stars.forEach((s, i) => {
      s.visible = dz > .3; if (!s.visible) return;
      const a = t * 3.2 + i * Math.PI * 2 / 3;
      s.position.set(this.tmp.x + Math.cos(a) * .55, this.tmp.y + .75 + Math.sin(t * 5 + i) * .05, this.tmp.z + Math.sin(a) * .55);
      s.lookAt(this.camera.position); s.rotation.z += t * 2;
    });
    // Alarm (liquidation) and blackout (bankruptcy).
    this.alarmT = Math.max(0, this.alarmT - dt);
    this.alarm.intensity = this.alarmT > 0 ? (Math.sin(t * 14) * .5 + .5) * 160 : 0;
    this.dark += (this.darkTarget - this.dark) * (1 - Math.exp(-dt * 1.5));
    this.lights.forEach((l, i) => { l.intensity = this.base[i] * (1 - .88 * this.dark); });
    this.monitorLight.intensity = 3 * (1 - this.dark);
    this.blackout.intensity = 60 * this.dark;
    // Camera shake without drifting the orbit.
    this.shakeAmp = Math.max(0, this.shakeAmp - dt * .25);
    this.lastShake.set((Math.random() - .5), (Math.random() - .5), (Math.random() - .5)).multiplyScalar(this.shakeAmp);
    this.camera.position.add(this.lastShake);
    this.renderer.render(this.scene, this.camera);
    if (this.faceRenderer && t - this.lastFace > this.faceStep) { this.faceRenderer.render(this.scene, this.faceCamera); this.lastFace = t; }
  }
}

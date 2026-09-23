// The real MaleCNS v1.0 point cloud (166,700 neurons at their measured soma positions) as a three.js
// Points layer. Each new observation replays the last 0.5 s of spikes as a wave that travels outward
// from the photoreceptors by synaptic hop distance; the decision neurons are drawn as larger dots.
import * as T from 'three';

const FAMS = [[60, 200, 255], [169, 139, 255], [255, 179, 71], [255, 122, 184]];
const famOf = s => (s.startsWith('ol_') || s.startsWith('visual_')) ? 0 : s.startsWith('vnc_') ? 2 : (s.startsWith('cb_') || s === 'ENS') ? 1 : 3;
const SPECIAL = [['dnp20_L', 0xff5d6c], ['dnp20_R', 0x2fd18a], ['gate', 0xffd166], ['reward', 0x2fd18a], ['aversive', 0xff5d6c], ['mbon', 0xc9b8ff]];

const vertex = `
attribute vec3 color; attribute float act; attribute float hop; attribute float special;
uniform float uWave; uniform float uPix; uniform float uTime;
varying vec3 vColor; varying float vAlpha;
void main(){
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  float reached = step(hop, uWave);
  float front = exp(-max(0.0, uWave - hop) * 7.0);
  float fire = reached * act * (0.55 + 0.45 * front);
  float sp = special * (0.75 + 0.25 * sin(uTime * 3.0));
  vColor = special > 0.0 ? color : mix(color, vec3(1.0, 0.86, 0.5), clamp(fire * 1.4, 0.0, 1.0));
  vAlpha = 0.055 + fire * 0.85 + sp * 0.9;
  gl_PointSize = (1.15 + fire * 2.6 + sp * 5.5) * uPix;
}`;
const fragment = `
varying vec3 vColor; varying float vAlpha;
void main(){
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  gl_FragColor = vec4(vColor, vAlpha * (1.0 - d * 1.6));
}`;

export class Brain {
  constructor(canvas, { lite = false } = {}) {
    this.canvas = canvas; this.ready = false; this.waveT = 99; this.time = 0;
    this.dpr = Math.min(devicePixelRatio, lite ? 1.5 : 2);
    this.renderer = new T.WebGLRenderer({ canvas, antialias: !lite, alpha: true });
    this.renderer.setPixelRatio(this.dpr);
    this.scene = new T.Scene();
    this.camera = new T.PerspectiveCamera(28, 1, .01, 50); this.camera.position.set(0, 0, 4.35);
    this.group = new T.Group(); this.group.rotation.set(.32, -.9, 0); this.scene.add(this.group);
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement); this.resize();
  }

  resize() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight; if (!w || !h) return;
    this.renderer.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
    if (this.material) this.material.uniforms.uPix.value = this.dpr * Math.max(.8, h / 420);
  }

  // `base` is where meta.json and the .bin files live: the dashboard root, or the web viewer's root.
  async load(base = '/') {
    const get = (u, kind) => fetch(base + u).then(r => { if (!r.ok) throw new Error(base + u); return kind === 'json' ? r.json() : r.arrayBuffer(); });
    const [meta, posBuf, scBuf, hopBuf] = await Promise.all([get('meta.json', 'json'), get('pos.bin'), get('sc.bin'), get('hop.bin')]);
    this.meta = meta; const n = meta.n;
    const P = new Float32Array(posBuf), SC = new Uint8Array(scBuf), HOP = new Uint8Array(hopBuf);
    const mn = meta.bounds_min, mx = meta.bounds_max;
    const c = [(mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2];
    const range = Math.max(mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]), s = 2.6 / range;
    const pos = new Float32Array(n * 3), col = new Float32Array(n * 3), hop = new Float32Array(n), special = new Float32Array(n);
    const famBySc = meta.superclasses.map(famOf);
    let maxHop = 1; for (let i = 0; i < n; i++) if (HOP[i] !== 255 && HOP[i] > maxHop) maxHop = HOP[i];
    const hopScale = Math.min(maxHop, 10);
    for (let i = 0; i < n; i++) {
      const x = P[3 * i];
      if (x !== x) { pos[3 * i] = 1e6; continue; }
      pos[3 * i] = (x - c[0]) * s; pos[3 * i + 1] = -(P[3 * i + 1] - c[1]) * s; pos[3 * i + 2] = (P[3 * i + 2] - c[2]) * s;
      const f = FAMS[famBySc[SC[i]]]; col[3 * i] = f[0] / 255; col[3 * i + 1] = f[1] / 255; col[3 * i + 2] = f[2] / 255;
      hop[i] = HOP[i] === 255 ? 1.1 + (i % 97) / 400 : Math.min(1, HOP[i] / hopScale);
    }
    const tint = new T.Color();
    for (const [key, hex] of SPECIAL) for (const i of meta.groups[key] || []) {
      tint.setHex(hex); col[3 * i] = tint.r; col[3 * i + 1] = tint.g; col[3 * i + 2] = tint.b; special[i] = 1;
    }
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.BufferAttribute(pos, 3));
    g.setAttribute('color', new T.BufferAttribute(col, 3));
    g.setAttribute('hop', new T.BufferAttribute(hop, 1));
    g.setAttribute('special', new T.BufferAttribute(special, 1));
    this.act = new T.BufferAttribute(new Float32Array(n), 1); g.setAttribute('act', this.act);
    this.material = new T.ShaderMaterial({
      vertexShader: vertex, fragmentShader: fragment, transparent: true, depthWrite: false, blending: T.AdditiveBlending,
      uniforms: { uWave: { value: 2 }, uPix: { value: 1 }, uTime: { value: 0 } },
    });
    this.points = new T.Points(g, this.material); this.points.frustumCulled = false; this.group.add(this.points);
    this.n = n; this.ready = true; this.resize();
  }

  // Spike counts of the last 0.5 s observation (uint8 per neuron) → brightness, then replay the wave.
  async refresh(url = '/counts.bin') {
    if (!this.ready) return;
    try {
      const buf = await fetch(url).then(r => { if (!r.ok) throw new Error(url); return r.arrayBuffer(); });
      const counts = new Uint8Array(buf); if (counts.length !== this.n) return;
      const a = this.act.array, L = Math.log(256); let total = 0;
      for (let i = 0; i < this.n; i++) { const c = counts[i]; a[i] = c ? Math.log1p(c) / L : 0; total += c; }
      this.act.needsUpdate = true; this.total = total; this.pulse();
    } catch { /* no checkpoint yet */ }
  }
  pulse() { this.waveT = 0; }

  render(dt) {
    if (!this.ready) return;
    this.time += dt; this.waveT += dt;
    this.material.uniforms.uWave.value = Math.min(1.4, this.waveT / 2.4 * 1.4);
    this.material.uniforms.uTime.value = this.time;
    this.group.rotation.y += dt * .12;
    this.renderer.render(this.scene, this.camera);
  }
}

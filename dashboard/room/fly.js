// Procedural fly character.
// Ported from "The Degeneret Fly" src/character.ts — Copyright (c) 2026 Robillionair OÜ, MIT License
// (see LICENSE-degeneretfly.txt). Changes for 초파리 트레이딩 챌린지: plain JavaScript, the gold chain is
// hidden until the room milestone unlocks it, extra gestures (dance, spin, faint, slump, slamLong,
// slamShort, cheer), a gesture queue, and a `pose` readout (chair swivel / tip, button impacts) that the
// studio applies to the chair and the desk buttons.
import * as T from 'three';

const sphere = new T.SphereGeometry(1, 32, 24);

export const DURATIONS = {
  win: 3.8, loss: 2.6, wave: 3.2, groom: 4.5, lean: 5.5, point: 3, shrug: 2.8, clap: 3, headbang: 3.4,
  stretch: 4, drum: 3.8, facepalm: 3, lookaround: 3.5, wingflex: 3, antenna: 3,
  dance: 5.6, spin: 1.7, faint: 6.5, slump: Infinity, slamLong: 2.4, slamShort: 2.4, cheer: 2.4,
};
const IDLE = ['lean', 'groom', 'lookaround', 'drum', 'antenna', 'wingflex', 'stretch', 'point', 'groom', 'headbang'];
const SLAM_AT = 0.95; // seconds into a slam gesture when the hand hits the button

export function makeFly() {
  const fly = new T.Group();
  const headParts = [], arms = [], wings = [], chainParts = [];
  const pivot = (parts, position) => {
    const p = new T.Group(); p.position.copy(position); fly.add(p); fly.updateMatrixWorld(true);
    for (const part of parts) p.attach(part);
    return p;
  };
  const skin = new T.MeshPhysicalMaterial({ color: 0x123f35, metalness: .6, roughness: .36, clearcoat: .42 });
  skin.onBeforeCompile = shader => {
    shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>',
      '#include <color_fragment>\n float grain=fract(sin(dot(vViewPosition.xyz,vec3(127.1,311.7,74.7)))*43758.5453); diffuseColor.rgb *= .76+.38*grain;');
  };
  const dark = new T.MeshStandardMaterial({ color: 0x12251e, roughness: .65, metalness: .45 });
  const gold = new T.MeshStandardMaterial({ color: 0xe5ad47, metalness: 1, roughness: .21 });
  const jewel = new T.MeshPhysicalMaterial({ color: 0xfcf0bd, metalness: .7, roughness: .09, clearcoat: 1 });
  const add = (material, pos, scale) => {
    const m = new T.Mesh(sphere, material); m.position.set(pos[0], pos[1], pos[2]); m.scale.set(scale[0], scale[1], scale[2]);
    m.castShadow = true; m.receiveShadow = true; fly.add(m); return m;
  };
  const tube = (points, radius, material) => {
    const curve = new T.CatmullRomCurve3(points.map(p => new T.Vector3(p[0], p[1], p[2])));
    const m = new T.Mesh(new T.TubeGeometry(curve, 20, radius, 8, false), material); m.castShadow = true; fly.add(m); return m;
  };
  add(skin, [0, 1.3, 0], [.47, .55, .35]); add(skin, [0, 1.05, .08], [.49, .37, .39]);
  for (let i = 0; i < 4; i++) {
    const band = new T.Mesh(new T.TorusGeometry(.43 - i * .015, .014, 8, 48), dark);
    band.rotation.x = Math.PI / 2; band.scale.y = .84; band.position.set(0, .91 + i * .115, .04); fly.add(band);
  }
  add(skin, [0, 1.72, 0], [.36, .32, .3]);
  headParts.push(add(skin, [0, 2.2, .08], [.48, .47, .39]));
  const eyeBase = new T.MeshPhysicalMaterial({ color: 0x831a48, metalness: .4, roughness: .29, clearcoat: .7 });
  const eyeMat = new T.MeshStandardMaterial({ color: 0xc44574, metalness: .65, roughness: .28, emissive: 0x000000 });
  for (const side of [-1, 1]) {
    const headStart = fly.children.length;
    add(eyeBase, [side * .31, 2.24, .3], [.285, .355, .25]);
    // Individually faceted compound eyes, placed on the ellipsoidal surface.
    const hex = new T.CylinderGeometry(.019, .019, .007, 6);
    const facets = new T.InstancedMesh(hex, eyeMat, 280); const dummy = new T.Object3D(); let k = 0;
    for (let row = -8; row <= 8; row++) for (let col = -8; col <= 8; col++) {
      const u = col * .108 + (row % 2) * .054, v = row * .105; if (u * u + v * v > .91) continue;
      const z = Math.sqrt(1 - u * u - v * v), normal = new T.Vector3(u / .285, v / .355, z / .25).normalize();
      dummy.position.set(side * .31 + u * .285, 2.24 + v * .355, .3 + z * .25);
      dummy.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), normal); dummy.updateMatrix();
      facets.setMatrixAt(k, dummy.matrix); facets.setColorAt(k, new T.Color().setHSL(.92 + Math.sin(k) * .015, .55, .22 + (k % 7) * .027)); k++;
    }
    facets.count = k; fly.add(facets);
    tube([[side * .22, 2.52, .06], [side * .3, 2.79, .04], [side * .43, 2.9, .14]], .028, skin);
    add(skin, [side * .43, 2.9, .14], [.046, .068, .044]);
    headParts.push(...fly.children.slice(headStart));
    // Legs, articulated feet, and three fingers on each hand.
    tube([[side * .25, .92, .04], [side * .32, .84, .51], [side * .29, -.12, .61]], .073, skin);
    add(dark, [side * .29, -.16, .70], [.12, .10, .23]);
    for (let toe = 0; toe < 3; toe++) tube([[side * .29 + (toe - 1) * .055, -.14, .76], [side * .29 + (toe - 1) * .074, -.20, .88]], .024, skin);
    const armStart = fly.children.length;
    const elbow = [side * .47, 1.29, .30], wrist = [side * .34, 1.30, .77];
    tube([[side * .33, 1.72, 0], elbow, wrist], .082, skin);
    add(skin, [side * .34, 1.33, .86], [.12, .045, .13]);
    for (let finger = 0; finger < 3; finger++) tube([[side * .34 + (finger - 1) * .065, 1.33, .86], [side * .34 + (finger - 1) * .068, 1.33, .98], [side * .34 + (finger - 1) * .066, 1.29, 1.01]], .022, skin);
    for (let ring = 0; ring < 3; ring++) {
      const b = new T.Mesh(new T.TorusGeometry(.095, .019, 8, 24), gold); b.position.set(side * .34, 1.32, .63 + ring * .05); fly.add(b);
    }
    const watch = add(gold, [side * .34, 1.405, .74], [.10, .024, .11]); watch.rotation.z = side * .15;
    add(jewel, [side * .34, 1.431, .74], [.072, .007, .085]);
    arms.push(pivot(fly.children.slice(armStart), new T.Vector3(side * .33, 1.72, 0)));
    // Paired translucent, veined wings behind the shoulders.
    const wingStart = fly.children.length;
    const shape = new T.Shape(); shape.moveTo(0, 0); shape.bezierCurveTo(.16, .34, .58, .38, .57, -.17); shape.bezierCurveTo(.5, -.67, .18, -.85, 0, 0);
    const wing = new T.Mesh(new T.ShapeGeometry(shape, 24), new T.MeshPhysicalMaterial({ color: 0xb8d4de, transparent: true, opacity: .33, roughness: .16, metalness: .15, side: T.DoubleSide, depthWrite: false }));
    wing.position.set(side * .12, 1.96, -.27); wing.scale.x = side; wing.rotation.y = side * .6; wing.rotation.z = side * -.28; fly.add(wing);
    for (let vein = 0; vein < 5; vein++) tube([[side * .13, 1.93, -.28], [side * (.24 + vein * .055), 1.75, -.35], [side * (.2 + vein * .07), 1.4 + vein * .06, -.37]], .003, new T.MeshBasicMaterial({ color: 0x81979c, transparent: true, opacity: .5 }));
    wings.push(pivot(fly.children.slice(wingStart), new T.Vector3(side * .12, 1.96, -.27)));
  }
  headParts.push(tube([[0, 2.22, .47], [0, 2.07, .60], [0, 1.98, .68]], .049, skin));
  const mouth = add(dark, [0, 1.98, .69], [.034, .031, .015]); headParts.push(mouth);
  const head = pivot(headParts, new T.Vector3(0, 2.2, .08));
  // Yaw first (hand moves sideways), then raise, then splay: raised arms open outward on rotation.z.
  arms.forEach(a => { a.rotation.order = 'ZXY'; });
  // Gold Cuban-link chain with pendant — earned at the 2,000 USDT room milestone.
  for (let i = 0; i < 44; i++) {
    const a = i / 44 * Math.PI * 2; const link = new T.Mesh(new T.TorusGeometry(.047, .013, 7, 12), gold);
    link.position.set(Math.sin(a) * .34, 1.77 - Math.max(0, Math.cos(a)) * .4, Math.cos(a) * .32 + .015);
    link.rotation.set(Math.PI / 3, (i % 2) * 1.1, -Math.sin(a) * .7); link.scale.set(1, .74, 1); fly.add(link); chainParts.push(link);
  }
  const pendant = new T.Mesh(new T.BoxGeometry(.22, .115, .03), gold); pendant.position.set(0, 1.35, .36); fly.add(pendant); chainParts.push(pendant);
  for (let i = 0; i < 21; i++) chainParts.push(add(jewel, [(i % 7 - 3) * .027, 1.32 + Math.floor(i / 7) * .029, .379], [.012, .012, .009]));
  const chain = pivot(chainParts, new T.Vector3(0, 1.5, 0)); chain.visible = false;
  const upper = pivot(fly.children.filter(p => p.position.y >= 1.3), new T.Vector3(0, 1.3, 0));

  let gesture = null, elapsed = 0, idleAt = 1, idleCount = 0;
  const queue = [], impacts = [];
  const pose = { swivel: 0, tip: 0, dizzy: 0 };
  const state = { dopamine: 0, octopamine: 0, serotonin: 1, acetylcholine: 0 };

  function start(next) { gesture = next; elapsed = 0; }
  function react(next) {
    if (gesture === 'slump') return;           // bankrupt: stays down until clear()
    queue.length = 0; start(next);
  }
  function then(next) { if (gesture) queue.push(next); else start(next); }
  function clear() { gesture = null; queue.length = 0; idleAt = 0; }

  function animate(time, dt, mood) {
    elapsed += dt;
    if (gesture && elapsed > DURATIONS[gesture]) {
      const done = gesture; gesture = null;
      if (queue.length) start(queue.shift()); else idleAt = time + (done === 'faint' ? 1.5 : .35);
    }
    if (!gesture && time > idleAt && mood.idle !== false) start(IDLE[idleCount++ % IDLE.length]);
    const blend = 1 - Math.exp(-dt * 4);
    for (const key of ['dopamine', 'octopamine', 'serotonin', 'acetylcholine']) {
      const target = Math.min(1, Math.max(0, mood.active ? mood[key] : key === 'serotonin' ? 1 : 0));
      state[key] += (target - state[key]) * blend;
    }
    const arousal = state.octopamine, focus = state.acetylcholine, calm = state.serotonin, reward = state.dopamine;
    upper.rotation.set(Math.sin(time * 1.7) * .008, 0, 0); upper.position.y = 1.3;
    head.rotation.set(-focus * .075 + Math.sin(time * (2.2 + reward * 2)) * .025,
      Math.sin(time * .75) * (.04 + (1 - calm) * .14), Math.sin(time * (1 + arousal * 2)) * (.02 + arousal * .10));
    arms.forEach((arm, i) => arm.rotation.set(Math.max(0, Math.sin(time * (4 + focus * 10) + i * Math.PI)) * (.015 + focus * .045), 0, 0));
    wings.forEach((wing, i) => { wing.rotation.set(0, Math.sin(time * (7 + arousal * 35) + i * Math.PI) * (.015 + arousal * .23), 0); });
    mouth.scale.y = .031; mouth.scale.z = .015;
    pose.swivel = 0; pose.tip = 0; pose.dizzy = 0;
    if (!gesture) return;
    const duration = DURATIONS[gesture];
    const env = Math.min(1, elapsed / .45, (duration - elapsed) / .65);
    const g = gesture;
    if (g === 'wave') {
      arms[1].rotation.set(-1.95 * env, Math.sin(elapsed * 12) * .25 * env, -.45 * env);
      head.rotation.y += .6 * env; upper.rotation.y = .16 * env;
    } else if (g === 'win' || g === 'cheer') {
      arms.forEach((arm, i) => arm.rotation.set((-2.05 + Math.sin(elapsed * 12) * .22) * env, 0, (i ? -.25 : .25) * env));
      upper.position.y += Math.abs(Math.sin(elapsed * 8)) * .07 * env; head.rotation.z += Math.sin(elapsed * 9) * .18 * env;
      wings.forEach((w, i) => { w.rotation.y += Math.sin(elapsed * 45 + i) * .7 * env; });
    } else if (g === 'loss') {
      // Wind up, land at the keyboard-height tabletop, recoil. No mesh penetration.
      const phase = elapsed % 1.05, raise = phase < .55 ? Math.sin(phase / .55 * Math.PI / 2) : Math.max(0, 1 - (phase - .55) / .10);
      arms.forEach((arm, i) => { arm.rotation.x = -(i ? .9 : 1.3) * raise * env; });
      upper.rotation.x = .06 * env; head.rotation.x += .2 * env; head.rotation.z += Math.sin(elapsed * 22) * .10 * env;
    } else if (g === 'groom') {
      arms.forEach((arm, i) => arm.rotation.set((-1.65 + Math.sin(elapsed * 9 + i) * .07) * env, (i ? -.13 : .13) * env, 0));
      head.rotation.x += .18 * env; head.rotation.z += Math.sin(elapsed * 5) * .07 * env;
    } else if (g === 'lean') {
      upper.rotation.x = .20 * env; head.rotation.x = -.14 * env;
      arms.forEach(arm => { arm.rotation.x = -.15 * env; });
    } else if (g === 'point') {
      arms[1].rotation.set(-.7 * env, -.2 * env, 0); head.rotation.y = -.22 * env;
    } else if (g === 'shrug' || g === 'stretch') {
      arms.forEach((arm, i) => arm.rotation.set(-(g === 'stretch' ? 2.4 : 1.1) * env, 0, (i ? -.45 : .45) * env));
      head.rotation.z = Math.sin(elapsed * 4) * .2 * env;
    } else if (g === 'clap') {
      arms.forEach((arm, i) => arm.rotation.set(-.9 * env, (i ? -1 : 1) * (.15 + .18 * Math.abs(Math.sin(elapsed * 8))) * env, 0));
    } else if (g === 'headbang') {
      head.rotation.x += Math.sin(elapsed * 9) * .32 * env; upper.rotation.x += Math.sin(elapsed * 9) * .055 * env;
    } else if (g === 'drum') {
      arms.forEach((arm, i) => { arm.rotation.x = -Math.max(0, Math.sin(elapsed * 11 + i * Math.PI)) * .6 * env; });
    } else if (g === 'facepalm' || g === 'antenna') {
      arms[0].rotation.set(-(g === 'antenna' ? 1.7 : 1.35) * env, -.16 * env, 0); head.rotation.x = .22 * env;
    } else if (g === 'lookaround') {
      head.rotation.y = Math.sin(elapsed * 2) * .55 * env; upper.rotation.y = Math.sin(elapsed * 2) * .08 * env;
    } else if (g === 'dance') {
      // Seated party dance: alternating disco arms, hip sway, bounce, wing buzz and a chair swivel.
      const beat = elapsed * 6.4;
      arms[0].rotation.set((-2.25 + Math.sin(beat) * .45) * env, 0, (.8 + Math.sin(beat) * .35) * env);
      arms[1].rotation.set((-2.25 + Math.sin(beat + Math.PI) * .45) * env, 0, -(.8 + Math.sin(beat + Math.PI) * .35) * env);
      upper.rotation.z = Math.sin(beat * .5) * .24 * env; upper.rotation.x = -.06 * env;
      upper.position.y += Math.abs(Math.sin(beat)) * .12 * env;
      head.rotation.z += Math.sin(beat * .5 + .6) * .3 * env; head.rotation.x += Math.sin(beat) * .16 * env;
      wings.forEach((w, i) => { w.rotation.y += Math.sin(elapsed * 48 + i) * .8 * env; });
      pose.swivel = Math.sin(beat * .5) * .85 * env;
      mouth.scale.y = .031 * (1 + Math.abs(Math.sin(elapsed * 9)) * 1.8 * env);
    } else if (g === 'spin') {
      const u = Math.min(1, elapsed / duration), ease = u < .5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
      pose.swivel = ease * Math.PI * 2;
      arms.forEach((arm, i) => arm.rotation.set(-.9 * env, 0, (i ? -.9 : .9) * env));
      head.rotation.x -= .15 * env; wings.forEach((w, i) => { w.rotation.y += Math.sin(elapsed * 50 + i) * .6 * env; });
    } else if (g === 'faint') {
      // Liquidated: falls back in the chair, arms flop up, wings droop, dizzy stars; recovers at the end.
      const fall = Math.min(1, elapsed / .55), out = Math.min(1, (duration - elapsed) / 1.2), k = fall * out;
      upper.rotation.x = -.72 * k; head.rotation.x = -.45 * k + Math.sin(elapsed * 2.2) * .06 * k;
      head.rotation.z = Math.sin(elapsed * 3.1) * .18 * k;
      arms.forEach((arm, i) => arm.rotation.set(-2.5 * k + Math.sin(elapsed * 4 + i) * .08 * k, 0, (i ? -.55 : .55) * k));
      wings.forEach((w, i) => { w.rotation.set((i ? -1 : 1) * .5 * k, 0, 0); });
      pose.tip = .34 * k; pose.dizzy = k;
    } else if (g === 'slump') {
      // Bankrupt: slumped over the desk, barely breathing.
      const k = Math.min(1, elapsed / 1.4);
      upper.rotation.x = .58 * k + Math.sin(time * .9) * .01; head.rotation.set(.55 * k, .25 * k, .1 * k);
      arms.forEach((arm, i) => arm.rotation.set(-.42 * k, (i ? -.3 : .3) * k, 0));
      wings.forEach((w, i) => { w.rotation.set((i ? -1 : 1) * .6 * k, 0, 0); });
    } else if (g === 'slamLong' || g === 'slamShort') {
      // Wind up and slam the big LONG (green, arms[0]) or SHORT (red, arms[1]) button, then point at the monitor.
      const i = g === 'slamLong' ? 0 : 1, arm = arms[i], other = arms[1 - i], yaw = (g === 'slamLong' ? -.5 : .5) * env;
      let x;
      if (elapsed < .75) x = -2.25 * Math.sin(elapsed / .75 * Math.PI / 2);
      else if (elapsed < SLAM_AT) x = -2.25 * (1 - (elapsed - .75) / (SLAM_AT - .75));
      else if (elapsed < 1.5) x = -.08 * Math.sin((elapsed - SLAM_AT) * 20) * Math.exp(-(elapsed - SLAM_AT) * 6);
      else x = -.75 * Math.min(1, (elapsed - 1.5) / .3);
      arm.rotation.set(x * env, yaw, 0);
      other.rotation.set(-.3 * env, 0, 0);
      upper.rotation.x = (elapsed > .75 && elapsed < 1.3 ? .12 : .02) * env;
      head.rotation.x += (elapsed > SLAM_AT && elapsed < 1.3 ? .22 : -.08) * env;
      if (elapsed - dt < SLAM_AT && elapsed >= SLAM_AT) impacts.push(g === 'slamLong' ? 'long' : 'short');
    } else {
      wings.forEach((w, i) => { w.rotation.y += (i ? 1 : -1) * (.45 + Math.sin(elapsed * 8) * .3) * env; });
    }
  }
  return {
    group: fly, head, arms, wings, chain, eyeMat, pose, impacts, animate, react, then, clear,
    get gesture() { return gesture; },
  };
}

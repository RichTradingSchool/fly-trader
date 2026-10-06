// Live studio: polls the read-only feed the dashboard server publishes, turns every new observation
// into a gesture and an on-screen event, and keeps the bottom HUD, the journal and the desk monitors
// current. The same page runs in three places:
//   * the local dashboard (/room/): the feed is the same server ('../tick.json', '../live.json');
//   * the static web viewer (GitHub Pages): window.FLY_SITE names feed.json, which names the feed;
//   * any copy with ?feed=https://…: an explicit feed.
// ?demo=1 plays a scripted season (every reaction in two minutes), ?choreo=1 adds gesture buttons,
// ?stream=1 hides everything interactive for an OBS browser source.
import { Studio } from './studio.js';
import { Brain } from './brain.js';
import { drawMain, drawSeason, drawStats } from './screens.js';

const $ = s => document.querySelector(s);
const params = new URLSearchParams(location.search);
const DEMO = params.has('demo'), CHOREO = params.has('choreo'), STREAM = params.has('stream');
const SITE = window.FLY_SITE || null;
const LITE = matchMedia('(max-width: 820px), (max-aspect-ratio: 1/1)').matches || params.has('lite');
const REASON = {
  'Already positioned': '이미 같은 방향 포지션 보유 중', 'Below breakeven': '수수료 보합 미만 — 보유 유지', 'Order cooldown': '주문 쿨다운(60초)',
  'Below minimum': '최소 주문 미만', 'Stale or future quote': '시세 지연', 'Spread limit': '호가 스프레드 과대', 'STOP file present': '운영자 정지',
  'Incomplete market snapshot': '시세 불완전', 'Invalid neural proposal': '잘못된 제안', 'Quote identity mismatch': '시세 종목 불일치',
  'Price moved beyond neural observation tolerance': '계산하는 동안 가격 급변',
};
const HALT = { 'market-outage': '시세 장애로 일시정지', bankrupt: '파산 — 챌린지 종료', 'accounting-error': '회계 오류로 정지', 'clock-skew': '시계 어긋남 — 점검 필요', 'Checkpoint integrity': '체크포인트 오류 — 점검 필요' };
const DISCLOSURE = [
  '페이퍼 트레이딩 · 실거래 없음 · 투자 자문 아님', '매매 규칙은 제작자가 설계했고 초파리 뇌는 신호만 만든다',
  '60초 관측이라 봉 내 순간 청산은 반영되지 않는다', '시세: OrangeX BTC 무기한(공개 API), 초기 차트 시드: Bybit 1분봉',
  '데이터: MaleCNS v1.0 CC BY 4.0 (FlyEM/HHMI Janelia 외) · 엔진: Stonkfly (MIT) · 대시보드: Bgihe (MIT) · 초파리 모델: Degeneret Fly (Robillionair OÜ, MIT)',
];
const num = (v, d = 2) => Number(v).toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });
const signed = (v, d = 2) => (Math.abs(v) < .005 ? '' : v > 0 ? '+' : '−') + num(Math.abs(v), d);
const kst = t => new Date(t * 1000).toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false });
const sideKo = s => (s === 'BUY' || s === 'LONG' ? '롱' : s === 'SELL' || s === 'SHORT' ? '숏' : '관망');
// Feed text goes into innerHTML in toasts, banners and the journal: never trust it as markup.
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let STATE = null, lastTick = null, SKEW = 0, overlay = null, FEED = null, V = null, FAILS = 0, OFFLINE = false, POLL = null;
const eyeImg = new Image();
// On the web viewer the eye frame comes from the feed's origin. Without a CORS request the 2D monitor
// canvas it is drawn into becomes tainted and WebGL refuses it as a texture (a black monitor).
eyeImg.crossOrigin = 'anonymous';
const mood = { dopamine: 0, octopamine: 0, serotonin: 1, acetylcholine: 0, active: true };
const liveUrl = name => `${FEED}${name}?v=${V}`;

if (STREAM) document.body.classList.add('stream');
await document.fonts.load('800 30px "Pretendard Variable"').catch(() => {});
const studio = new Studio($('#studio'), $('#facecam'), { lite: LITE });
const brain = new Brain($('#brain'), { lite: LITE });
// Static brain files sit next to the page's parent (dashboard root, or the web viewer's root).
brain.load('../').then(() => { if (FEED && V && !OFFLINE) brain.refresh(liveUrl('counts.bin')); })
  .catch(err => { $('#brainNote').textContent = '뇌 데이터를 불러오지 못했습니다'; console.warn(err); });
$('#home').onclick = () => studio.home();
window.__room = { studio, brain };  // console handle for checks and live tuning

// ---- about panel -----------------------------------------------------------------------------------
const about = $('#about');
$('#aboutBtn').onclick = () => { about.hidden = false; };
about.addEventListener('click', ev => { if (ev.target === about || ev.target.closest('[data-close]')) about.hidden = true; });
addEventListener('keydown', ev => { if (ev.key === 'Escape') about.hidden = true; });

// ---- helpers -----------------------------------------------------------------------------------------
const last = s => { const ev = s?.events || []; return ev[ev.length - 1] || null; };
function running(s) {
  const e = last(s); if (!s || !e || s.stopped || s.ledger?.halted) return false;
  return Date.now() / 1000 + SKEW - e.time < 180;
}
function decisionLine(e) {
  if (!e) return '';
  const call = e.side === 'BUY' ? '롱 신호' : e.side === 'SELL' ? '숏 신호' : '관망';
  return `DNp20 좌 ${num(e.left_hz, 0)} Hz · 우 ${num(e.right_hz, 0)} Hz · 게이트 ${e.gate}회 → ${call}`;
}
function outcomeLine(e) {
  if (!e) return '';
  if (e.execution === 'BANKRUPT') return '파산 — 더 이상 최소 주문을 낼 수 없음';
  const liq = e.liquidation ? `강제청산 ${signed(+e.liquidation.realized_net)} USDT · ` : '';
  if (e.execution === 'FILLED') {
    const close = (e.fills || []).find(f => f.action === 'FLIP_CLOSE');
    return liq + (close ? `${sideKo(close.side)} 청산 ${signed(+close.realized_net)} USDT → ${sideKo(e.side)} 진입` : `${sideKo(e.side)} 진입 체결`);
  }
  if (e.execution === 'VETO') return liq + (REASON[e.reason] || e.reason || '거부');
  return liq + '주문 없음';
}
function toast(html, kind = '') {
  const el = document.createElement('div'); el.className = `toast ${kind}`; el.innerHTML = html; $('#toasts').prepend(el);
  setTimeout(() => el.classList.add('out'), 5200); setTimeout(() => el.remove(), 6000);
  while ($('#toasts').children.length > 4) $('#toasts').lastChild.remove();
}
function flashStage(kind, ms) {
  const st = $('.stage'); st.classList.remove('alarm', 'win'); void st.offsetWidth; st.classList.add(kind);
  clearTimeout(flashStage.t); flashStage.t = setTimeout(() => st.classList.remove(kind), ms);
}
function banner(text, sub, kind) {
  const b = $('#banner'); b.className = `banner ${kind}`; b.innerHTML = `<b>${esc(text)}</b>${sub ? `<span>${esc(sub)}</span>` : ''}`;
  void b.offsetWidth; b.classList.add('show'); clearTimeout(banner.t); banner.t = setTimeout(() => b.classList.remove('show'), 3200);
  overlay = { text, sub, color: { long: '#2fd18a', short: '#ff4d5e', good: '#ffd166', bad: '#ff4d5e', gold: '#ffd166' }[kind] || '#eef0fa', t0: performance.now(), dur: 2600 };
}

// ---- reactions -----------------------------------------------------------------------------------------
function reactTo(e) {
  if (e.execution === 'BANKRUPT') {
    studio.setBankrupt(true); studio.react('slump'); studio.cut('face', 8); flashStage('alarm', 3000);
    banner('파산', '챌린지 종료 — 최소 주문도 낼 수 없는 잔고', 'bad'); return;
  }
  const slam = e.side === 'BUY' ? 'slamLong' : 'slamShort';
  const lev = STATE?.settings?.leverage || e.position?.leverage || 20;
  if (e.liquidation) {
    studio.react('faint'); studio.alarmOn(4.5); studio.cut('face', 5.5); flashStage('alarm', 4500);
    banner('강제청산!', `${sideKo(e.liquidation.side)} 포지션 증거금 ${num(Math.abs(+e.liquidation.realized_net))} USDT 증발`, 'bad');
    toast(`<b>🚨 강제청산</b> ${sideKo(e.liquidation.side)} @ ${num(+e.liquidation.price, 1)}`, 'bad');
    if (e.execution === 'FILLED') studio.then(slam);
    return;
  }
  if (e.execution === 'FILLED') {
    const close = (e.fills || []).find(f => f.action === 'FLIP_CLOSE');
    if (close) {
      const net = +close.realized_net;
      if (net >= 0) {
        studio.react('dance'); studio.burstConfetti(); studio.then('spin'); studio.then(slam); studio.cut('face', 6.8); flashStage('win', 2600);
        banner(`익절 +${num(net)} USDT`, `${sideKo(close.side)} 청산 → ${sideKo(e.side)}로 뒤집기`, 'good');
        toast(`<b>💸 익절</b> +${num(net)} USDT · ${sideKo(e.side)}로 뒤집기`, 'good');
      } else {
        studio.react('loss'); studio.then(slam); studio.cut('face', 3.2);
        banner(`손절 ${signed(net)} USDT`, `${sideKo(close.side)} 청산 → ${sideKo(e.side)}로 뒤집기`, 'bad');
      }
    } else {
      studio.react(slam); studio.cut('desk', 2.6);
      banner(`${sideKo(e.side)} 진입!`, `${num(+(e.position?.qty || 0), 3)} BTC · ${lev}배`, e.side === 'BUY' ? 'long' : 'short');
      toast(`<b>${e.side === 'BUY' ? '🟢 롱' : '🔴 숏'} 진입</b> @ ${num(+e.bid, 1)}`, e.side === 'BUY' ? 'long' : 'short');
    }
  } else if (e.execution === 'VETO') {
    if (e.reason === 'Below breakeven') studio.react('shrug');
    else if (e.reason === 'Already positioned') studio.react('point');
    else if (e.reason === 'Order cooldown') studio.react('drum');
    else studio.react('facepalm');
  } else {
    if (e.stimulus === 'reward' && e.pnl > 4) studio.react('headbang');
    else if (e.stimulus === 'aversive' && e.pnl < -4) studio.react('facepalm');
    else studio.react('lean');
  }
  if (e.funding) {
    const paid = +e.funding.fee;
    toast(`<b>⏱ 펀딩 ${paid <= 0 ? '수취' : '지불'}</b> ${signed(-paid)} USDT`, paid <= 0 ? 'good' : 'bad');
    if (paid <= 0 && !e.liquidation && e.execution !== 'FILLED') studio.react('cheer');
  }
}
function roomToasts(e) {
  for (const r of e.room_events || []) {
    const label = esc(r.label);
    if (r.type === 'unlock') { toast(`<b>🏆 ${label} 획득!</b> 순자산 ${num(r.equity_threshold, 0)} USDT 돌파`, 'gold'); banner(`${r.label} 획득!`, `순자산 ${num(r.equity_threshold, 0)} USDT 돌파`, 'gold'); studio.then('cheer'); }
    else { toast(`<b>📦 ${label} 압류</b> 순자산 ${num(r.equity_threshold, 0)} USDT 아래로`, 'bad'); studio.then('facepalm'); }
  }
}

// ---- HUD, journal, monitors ------------------------------------------------------------------------
function status(s) {
  const lg = s.ledger || {}, st = $('#status');
  if (OFFLINE) { st.textContent = '데모 · 오프라인'; st.className = 'pill warn'; return; }
  st.textContent = s.stopped ? '운영자 정지' : lg.halted ? (HALT[lg.halted] || `정지: ${lg.halted}`) : running(s) ? 'LIVE · 페이퍼' : '대기 중';
  st.className = `pill ${lg.halted === 'bankrupt' || s.stopped ? 'bad' : lg.halted ? 'warn' : running(s) ? 'live' : 'warn'}`;
}
function hud(s) {
  const e = last(s), lg = s.ledger || {}, init = +(lg.initial_cash || 1000);
  const eq = e ? e.equity : +(lg.equity || init), roi = (eq / init - 1) * 100;
  $('#equity').textContent = num(eq, 2);
  const r = $('#roi'); r.textContent = `${signed(roi, 2)}%`; r.className = roi >= 0 ? 'up' : 'down';
  const pos = e?.position;
  const ps = $('#posSide'); ps.textContent = pos ? `${sideKo(pos.side)} ${pos.leverage || 20}×` : '없음'; ps.className = pos ? String(pos.side).toLowerCase() : '';
  $('#posDetail').textContent = pos ? `${num(+pos.qty, 3)} BTC @ ${num(+pos.entry, 1)} · 청산가 ${num(+pos.liquidation_price, 1)}` : '관망 중';
  // Five-digit amounts drop the cents so a rich season still fits its HUD cell.
  const cents = v => (Math.abs(v) >= 10000 ? 0 : 2), USDT = '<i class="unit">USDT</i>';
  const up = pos ? +pos.unrealized : 0, u = $('#upnl'); u.innerHTML = pos ? `${signed(up, cents(up))}${USDT}` : '–'; u.className = up >= 0 ? 'up' : 'down';
  const rp = +(lg.realized_pnl || 0), rr = $('#realized'); rr.innerHTML = `${signed(rp, cents(rp))}${USDT}`; rr.className = rp >= 0 ? 'up' : 'down';
  const fee = +(lg.fees_paid || 0); $('#fees').innerHTML = `${fee > .005 ? '−' : ''}${num(fee, cents(fee))}${USDT}`;
  $('#btc').textContent = e ? num(+e.bid, 1) : '–';
  $('#trades').textContent = `${s.orders_today ?? 0}회`;
  $('#tick').textContent = e ? e.tick.toLocaleString('ko-KR') : '–';
  $('#flyName').textContent = s.fly_name || '초파리';
  const set = s.settings || {}, lev = set.leverage || 20, run = String(s.run || 's1');
  $('#seasonTag').textContent = `${/^s\d+$/.test(run) ? `시즌 ${run.slice(1)}` : run} · BTC ${lev}배 페이퍼`;
  document.querySelectorAll('#about .lev').forEach(x => { x.textContent = lev; });
  if (set.capital) document.querySelectorAll('#about .capital').forEach(x => { x.textContent = num(+set.capital, 0); });
  if (set.margin_fraction) document.querySelectorAll('#about .margin').forEach(x => { x.textContent = Math.round(+set.margin_fraction * 100); });
  status(s);
  $('#thought').textContent = e ? `${decisionLine(e)} · ${outcomeLine(e)}` : '';
  $('#credits').textContent = (s.disclosure?.length ? s.disclosure : DISCLOSURE).join('  ·  ');
  meter(e);
  tickClock();
}
function meter(e) {
  if (!e) return;
  const w = (id, v) => { $(id).style.width = `${Math.max(0, Math.min(100, v))}%`; };
  w('#barL', e.left_hz / 80 * 100); w('#barR', e.right_hz / 80 * 100); w('#barG', (e.gate || 0) / 12 * 100);
  w('#barD', Math.max(e.reward_spikes || 0, e.aversive_spikes || 0) / 150 * 100);
  $('#hzL').textContent = `${num(e.left_hz, 0)}Hz`; $('#hzR').textContent = `${num(e.right_hz, 0)}Hz`; $('#gateN').textContent = `${e.gate}회`;
  $('#dopa').textContent = e.stimulus === 'reward' ? '보상' : e.stimulus === 'aversive' ? '처벌' : '—';
  const d = e.right_hz - e.left_hz;
  const call = e.side === 'BUY' ? '<span class="long">롱 신호</span>' : e.side === 'SELL' ? '<span class="short">숏 신호</span>' : '관망';
  $('#verdict').innerHTML = `우 − 좌 = ${d >= 0 ? '+' : '−'}${num(Math.abs(d), 0)} Hz · 게이트 ${Number(e.gate) || 0}회 → ${call}`;
}
function tickClock() {
  const s = STATE; if (!s) return; const lg = s.ledger || {};
  const t0 = +lg.started_at || 0, now = Date.now() / 1000 + SKEW;
  $('#day').textContent = t0 ? Math.floor((now - t0) / 86400) + 1 : '–';
  const nf = +lg.next_funding || 0;
  if (nf) { const m = Math.max(0, Math.round((nf / 1000 - now) / 60)); $('#funding').textContent = `${Math.floor(m / 60)}시간 ${m % 60}분`; }
}
function journalEvents(s) {
  // live.json carries the last two hours plus older trades separately; merge them by tick.
  const byTick = new Map();
  for (const e of [...(s.notable || []), ...(s.events || [])]) byTick.set(e.tick, e);
  return [...byTick.values()].sort((a, b) => a.tick - b.tick);
}
function journal(s) {
  const items = [];
  for (const e of journalEvents(s)) {
    if (e.liquidation) items.push({ t: e.time, k: 'bad', label: `${sideKo(e.liquidation.side)} 강제청산`, price: +e.liquidation.price, net: +e.liquidation.realized_net });
    for (const f of e.fills || []) {
      if (f.action === 'OPEN') items.push({ t: e.time, k: f.side === 'LONG' ? 'long' : 'short', label: `${sideKo(f.side)} 진입`, price: +f.price });
      else if (f.action === 'FLIP_CLOSE') items.push({ t: e.time, k: +f.realized_net >= 0 ? 'good' : 'bad', label: `${sideKo(f.side)} 청산`, price: +f.price, net: +f.realized_net });
      else if (f.action === 'FLIP_OPEN') items.push({ t: e.time, k: f.side === 'LONG' ? 'long' : 'short', label: `${sideKo(f.side)} 진입 (뒤집기)`, price: +f.price });
      else if (f.action === 'BANKRUPT') items.push({ t: e.time, k: 'bad', label: '파산' });
    }
    if (e.funding) items.push({ t: e.time, k: +e.funding.fee <= 0 ? 'good' : 'bad', label: `펀딩 ${+e.funding.fee <= 0 ? '수취' : '지불'}`, net: -(+e.funding.fee) });
    for (const r of e.room_events || []) items.push({ t: e.time, k: r.type === 'unlock' ? 'gold' : 'bad', label: `${r.type === 'unlock' ? '획득' : '압류'} · ${esc(r.label)}` });
  }
  $('#journal').innerHTML = items.slice(-11).reverse().map(i =>
    `<li class="${i.k}"><time>${kst(i.t)}</time><b>${i.label}</b><span>${i.price ? num(i.price, 1) : ''}</span><em>${i.net !== undefined ? `${signed(i.net, Math.abs(i.net) >= 10000 ? 0 : 2)}` : ''}</em></li>`).join('')
    || '<li class="empty">아직 체결이 없습니다</li>';
}
function mainView() {
  const s = STATE, e = last(s), pos = e?.position, ev = s?.events || [], seed = s?.season?.seed_bid;
  let ov = null;
  if (overlay) { const a = 1 - (performance.now() - overlay.t0) / overlay.dur; if (a > 0) ov = { ...overlay, alpha: Math.min(1, a * 2.2) }; else overlay = null; }
  return {
    tick: e?.tick, live: OFFLINE ? false : running(s), bid: e ? +e.bid : null, change: seed && e ? +e.bid / seed - 1 : null,
    bids: ev.slice(-120).map(x => +x.bid).filter(Number.isFinite), side: pos?.side, qty: pos ? +pos.qty : 0,
    entry: pos ? +pos.entry : null, liq: pos ? +pos.liquidation_price : null, upnl: pos ? +pos.unrealized : 0,
    upnlPct: pos ? +pos.unrealized / +pos.margin * 100 : 0, eye: eyeImg, decision: decisionLine(e), outcome: outcomeLine(e), overlay: ov,
  };
}
function sideScreens(s) {
  const lg = s.ledger || {}, pts = s.season?.points || [], init = +(lg.initial_cash || 1000);
  if (studio.items.dual_monitor.visible) drawSeason(studio.screens.second, { season: pts, seedBid: s.season?.seed_bid, init });
  if (studio.items.triple_monitor_leather_chair.visible) drawStats(studio.screens.third, {
    best: Math.max(init, ...pts.map(p => p.equity)), realized: +(lg.realized_pnl || 0), fees: +(lg.fees_paid || 0),
    funding: +(lg.funding_paid || 0), liquidations: +(lg.liquidations || 0), unlocked: (lg.room_unlocked || []).length,
  });
}

// ---- state intake ---------------------------------------------------------------------------------------
const scripted = () => DEMO || OFFLINE;
function onState(s) {
  STATE = s; if (s.now) SKEW = s.now - Date.now() / 1000;
  const ev = s.events || [], e = last(s);
  if (lastTick === null) {
    lastTick = e ? e.tick : 0;
    studio.setUnlocked(s.ledger?.room_unlocked || [], false);
    if (s.ledger?.halted === 'bankrupt') { studio.setBankrupt(true); studio.react('slump'); } else studio.react('wave');
    if (e && V && !OFFLINE) eyeImg.src = liveUrl('input.png');
  } else {
    const fresh = ev.filter(x => x.tick > lastTick);
    if (fresh.length) {
      lastTick = fresh[fresh.length - 1].tick;
      // After a long background pause only the newest observation gets a reaction; the journal still has all.
      (fresh.length > 3 ? fresh.slice(-1) : fresh).forEach(x => { reactTo(x); roomToasts(x); });
      if (!scripted()) { eyeImg.src = liveUrl('input.png'); brain.refresh(liveUrl('counts.bin')); } else brain.pulse();
    }
    studio.setUnlocked(s.ledger?.room_unlocked || [], true);
    if (s.ledger?.halted !== 'bankrupt') studio.setBankrupt(false);
  }
  if (e) Object.assign(mood, {
    dopamine: Math.min(1, (e.reward_spikes || 0) / 40), octopamine: Math.min(1, Math.abs(e.pnl || 0) / 12),
    serotonin: e.side === 'HOLD' ? .9 : .35, acetylcholine: Math.min(1, (e.gate || 0) / 8), active: OFFLINE || running(s),
  });
  hud(s); journal(s); sideScreens(s);
}

// ---- feed --------------------------------------------------------------------------------------------
const slash = u => (u.endsWith('/') ? u : `${u}/`);
async function resolveFeed() {
  const q = params.get('feed');
  if (q && /^(https:\/\/|http:\/\/(127\.0\.0\.1|localhost)[:/])/.test(q)) return slash(q);
  if (!SITE) return '../';
  try {
    const f = await fetch(`${SITE.feedIndex}?t=${Date.now()}`, { cache: 'no-store' }).then(r => r.json());
    if (typeof f.feed === 'string' && /^https?:\/\//.test(f.feed)) return slash(f.feed);
  } catch { /* no feed published yet */ }
  return null;
}
const getJson = url => fetch(url, { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error(`${r.status} ${url}`); return r.json(); });
async function poll() {
  try {
    if (!FEED) throw new Error('no feed');
    const t = await getJson(`${FEED}tick.json`);
    FAILS = 0; SKEW = (t.now || Date.now() / 1000) - Date.now() / 1000;
    if (t.v !== V) {
      const s = await fetch(`${FEED}live.json?v=${t.v}`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
      const first = V === null; V = t.v; onState(s);
      if (first && !DEMO) brain.refresh(liveUrl('counts.bin'));
    } else if (STATE) status(STATE);
  } catch (err) {
    FAILS += 1;
    if (SITE && !STATE && FAILS >= 2) return goOffline();
    if (SITE && FAILS % 3 === 0) {
      // A quick tunnel gets a new address when it restarts; feed.json follows it, so look again.
      const f = await resolveFeed();
      if (f && f !== FEED) { FEED = f; V = null; $('#labLink').href = FEED; }
    }
    const st = $('#status'); st.textContent = '서버 연결 대기…'; st.className = 'pill warn';
  }
}
function goOffline() {
  if (OFFLINE) return;
  OFFLINE = true; clearInterval(POLL);
  $('#offline').hidden = false; $('#labLink').hidden = true;
  eyeImg.src = 'sample-eye.png';
  lastTick = null; demo();
  // Keep looking for the live feed; switch over by reloading once it answers.
  setInterval(async () => {
    const f = await resolveFeed();
    if (f && await fetch(`${f}tick.json`, { cache: 'no-store' }).then(r => r.ok).catch(() => false)) location.reload();
  }, 30000);
}

// ---- demo season -------------------------------------------------------------------------------------
function demo() {
  const milestones = [[1200, 'coffee_machine', '커피머신'], [1500, 'dual_monitor', '듀얼 모니터'], [2000, 'gold_chain', '금목걸이'], [3000, 'triple_monitor_leather_chair', '트리플 모니터 + 가죽의자'], [5000, 'luxury_sedan', '고급 세단'], [10000, 'yacht', '요트'], [20000, 'gold_bars', '금괴 더미'], [50000, 'helicopter', '헬기']];
  const t0 = Date.now() / 1000 - 3600 * 5;
  let bid = 86400, eq = 1000, tick = 0, pos = null, unlocked = [], realized = 0, fees = 0, halted = null, step = 0;
  const s = { events: [], ledger: {}, season: { seed_bid: bid, points: [] }, disclosure: STATE?.disclosure || DISCLOSURE, fly_name: STATE?.fly_name || '초파리', orders_today: 0, now: Date.now() / 1000 };
  const script = [
    ['hold'], ['open', 'BUY'], ['veto', 'BUY', 'Already positioned'], ['hold'], ['veto', 'SELL', 'Below breakeven'],
    ['flip', 'SELL', 1310], ['hold'], ['flip', 'BUY', 1720], ['funding'], ['flip', 'SELL', 2300], ['hold'],
    ['flip', 'BUY', 3400], ['flip', 'SELL', 5600], ['flip', 'BUY', 11000], ['flip', 'SELL', 23000], ['flip', 'BUY', 52000],
    ['liquidation', null, 1400], ['open', 'SELL'], ['bankrupt'], ['reset'],
  ];
  function push(kind, side, arg) {
    tick += 1; bid *= 1 + (Math.random() - .5) * .004; const time = Date.now() / 1000 - Math.max(0, 25 - tick) * 60;
    const e = { tick, time, bid: bid.toFixed(1), side: side || 'HOLD', execution: 'HOLD', reason: null, action: null, fills: [], liquidation: null, funding: null, room_events: [],
      left_hz: 30 + Math.random() * 20, right_hz: 30 + Math.random() * 20, gate: Math.floor(Math.random() * 6), stimulus: 'none', reward_spikes: 0, pnl: (Math.random() - .5) * 6, equity: eq };
    const fill = (action, sd, net = 0) => ({ action, side: sd, price: bid.toFixed(1), qty: '0.080', realized_net: String(net) });
    if (kind === 'open') { pos = side === 'BUY' ? 'LONG' : 'SHORT'; e.execution = 'FILLED'; e.action = 'OPEN'; e.fills = [fill('OPEN', pos)]; fees += 3.9; s.orders_today++; }
    else if (kind === 'veto') { e.execution = 'VETO'; e.reason = arg; }
    else if (kind === 'flip') {
      const net = arg - eq; realized += net; eq = arg; const was = pos; pos = side === 'BUY' ? 'LONG' : 'SHORT';
      e.execution = 'FILLED'; e.action = 'FLIP'; e.fills = [fill('FLIP_CLOSE', was, net.toFixed(2)), fill('FLIP_OPEN', pos)]; e.stimulus = 'reward'; e.reward_spikes = 30; fees += 7.8; s.orders_today++;
    } else if (kind === 'funding') e.funding = { fee: '-0.60' };
    else if (kind === 'liquidation') { e.liquidation = { side: pos, price: bid.toFixed(1), realized_net: (arg - eq).toFixed(2) }; realized += arg - eq; eq = arg; pos = null; }
    else if (kind === 'bankrupt') { e.execution = 'BANKRUPT'; eq = 9.5; pos = null; halted = 'bankrupt'; }
    e.equity = eq;
    e.position = pos ? { side: pos, qty: '0.080', entry: (bid * (pos === 'LONG' ? .999 : 1.001)).toFixed(1), margin: '330', unrealized: (e.pnl * 3).toFixed(2), liquidation_price: (bid * (pos === 'LONG' ? .955 : 1.045)).toFixed(1), leverage: 20 } : null;
    const want = milestones.filter(m => eq >= m[0]).map(m => m[1]);
    for (const m of milestones) {
      if (want.includes(m[1]) && !unlocked.includes(m[1])) e.room_events.push({ type: 'unlock', item: m[1], label: m[2], equity_threshold: m[0] });
      if (!want.includes(m[1]) && unlocked.includes(m[1])) e.room_events.push({ type: 'repossess', item: m[1], label: m[2], equity_threshold: m[0] });
    }
    unlocked = want;
    s.events.push(e); s.events = s.events.slice(-400);
    s.season.points.push({ tick, time, equity: eq, bid: +bid.toFixed(1), liq: !!e.liquidation, bankrupt: e.execution === 'BANKRUPT' });
    s.ledger = { initial_cash: '1000', equity: String(eq), realized_pnl: String(realized), fees_paid: String(fees), funding_paid: '-0.6', liquidations: s.events.filter(x => x.liquidation).length,
      next_funding: (Date.now() + 3 * 3600e3), started_at: t0, room_unlocked: unlocked, halted, position: pos };
    s.now = Date.now() / 1000; onState(JSON.parse(JSON.stringify(s)));
  }
  for (let i = 0; i < 25; i++) push('hold');
  const next = () => {
    const [kind, side, arg] = script[step++ % script.length];
    if (kind === 'reset') { eq = 1000; pos = null; unlocked = []; realized = 0; fees = 0; halted = null; s.orders_today = 0; studio.fly.clear(); studio.setBankrupt(false); push('hold'); return kind; }
    push(kind, side, arg); return kind;
  };
  window.__room.step = next;
  setInterval(next, 7500);
}

// ---- choreography preview --------------------------------------------------------------------------
if (CHOREO) {
  const box = document.createElement('div'); box.className = 'choreo';
  const moves = ['dance', 'spin', 'slamLong', 'slamShort', 'faint', 'slump', 'cheer', 'win', 'loss', 'wave', 'groom', 'lean', 'point', 'shrug', 'clap', 'headbang', 'stretch', 'drum', 'facepalm', 'lookaround', 'wingflex', 'antenna'];
  box.innerHTML = moves.map(m => `<button data-m="${m}">${m}</button>`).join('') + '<button data-x="all">아이템 전부</button><button data-x="none">압류</button><button data-x="confetti">색종이</button><button data-x="alarm">경보</button><button data-x="dark">파산 조명</button><button data-x="clear">초기화</button>';
  box.onclick = ev => {
    const b = ev.target.closest('button'); if (!b) return;
    const m = b.dataset.m;
    if (m) {
      studio.fly.clear(); studio.react(m);
      if (m === 'faint') { studio.alarmOn(4); flashStage('alarm', 4000); }
      if (m === 'dance') { studio.burstConfetti(); flashStage('win', 2600); }
      if (['dance', 'faint', 'slump', 'cheer', 'win', 'loss', 'facepalm', 'groom', 'wave'].includes(m)) studio.cut('face', 4.5);
      if (m === 'slamLong' || m === 'slamShort') studio.cut('desk', 2.6);
    }
    const x = b.dataset.x;
    if (x === 'all') studio.setUnlocked(Object.keys(studio.items), true);
    if (x === 'none') studio.setUnlocked([], true);
    if (x === 'confetti') studio.burstConfetti();
    if (x === 'alarm') studio.alarmOn(4);
    if (x === 'dark') studio.setBankrupt(studio.darkTarget < .5);
    if (x === 'clear') { studio.fly.clear(); studio.setBankrupt(false); }
  };
  $('.stage').append(box);
}

// ---- loops -------------------------------------------------------------------------------------------
let prev = performance.now();
function frame(t) {
  const dt = Math.min(.05, (t - prev) / 1000); prev = t;
  studio.render(dt, { ...mood, idle: true }); brain.render(dt);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
setInterval(() => { if (STATE) drawMain(studio.screens.main, mainView()); }, 125);
setInterval(tickClock, 1000);

FEED = await resolveFeed();
if (SITE) {
  $('#siteHome').hidden = false;
  if (/^https:\/\//.test(SITE.community || '')) { const c = $('#community'); c.href = SITE.community; c.hidden = false; }
  if (FEED) $('#labLink').href = FEED; else $('#labLink').hidden = true;
}
if (DEMO) { await poll().catch(() => {}); lastTick = null; demo(); }
else if (SITE && !FEED) goOffline();
else { await poll(); POLL = setInterval(poll, 3000); }

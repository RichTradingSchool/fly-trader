// Canvas drawings for the desk monitors. Everything here reads a plain `view` object built by app.js.
const FONT = '"Pretendard Variable", Pretendard, "Malgun Gothic", sans-serif';
const C = { bg: '#0b101a', panel: '#111827', line: '#243049', text: '#eef0fa', mute: '#8e99af', long: '#2fd18a', short: '#ff4d5e', gold: '#ffd166', violet: '#ad9ff8', amber: '#ffb347' };
const num = (v, d = 1) => Number(v).toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });
const signed = (v, d = 2) => (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(v), d);
const font = (w, px) => `${w} ${px}px ${FONT}`;

function dashed(ctx, x0, x1, y, color, label, align = 'right') {
  ctx.save(); ctx.strokeStyle = color; ctx.setLineDash([10, 8]); ctx.lineWidth = 2.5;
  ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke(); ctx.setLineDash([]);
  ctx.font = font(700, 18); ctx.fillStyle = color; ctx.textAlign = align; ctx.fillText(label, align === 'right' ? x1 - 4 : x0 + 4, y - 8); ctx.restore();
}

export function drawMain(scr, v) {
  const { ctx } = scr, W = 1280, H = 768;
  ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
  ctx.textBaseline = 'alphabetic';
  // Header.
  ctx.fillStyle = C.text; ctx.font = font(800, 30); ctx.textAlign = 'left'; ctx.fillText('BTC-USDT 무기한', 38, 52);
  ctx.fillStyle = C.mute; ctx.font = font(500, 18); ctx.fillText('OrangeX 공개 시세 · 페이퍼 20×', 290, 50);
  ctx.textAlign = 'right'; ctx.font = font(700, 18);
  ctx.fillStyle = v.live ? (Math.floor(Date.now() / 600) % 2 ? C.long : '#1c7a52') : C.amber;
  ctx.fillText(v.live ? '● LIVE' : '○ 대기', W - 38, 50);
  ctx.fillStyle = C.mute; ctx.fillText(v.tick ? `${v.tick}번째 관측` : '', W - 140, 50);
  ctx.strokeStyle = C.line; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(35, 74); ctx.lineTo(W - 35, 74); ctx.stroke();
  // Price.
  ctx.textAlign = 'left'; ctx.fillStyle = C.text; ctx.font = font(800, 66); ctx.fillText(v.bid ? num(v.bid, 1) : '—', 38, 152);
  ctx.font = font(500, 18); ctx.fillStyle = C.mute; ctx.fillText('매수호가 (USDT)', 40, 184);
  if (v.change !== null && v.change !== undefined) {
    ctx.font = font(700, 24); ctx.fillStyle = v.change >= 0 ? C.long : C.short;
    ctx.fillText(`${v.change >= 0 ? '▲' : '▼'} ${signed(v.change * 100, 2)}% 시즌 시작 대비`, 330, 146);
  }
  // Chart of recent bids with entry and liquidation lines.
  const x0 = 40, x1 = 800, y0 = 222, y1 = 560, pts = v.bids || [];
  ctx.fillStyle = C.panel; ctx.fillRect(x0 - 4, y0 - 12, x1 - x0 + 8, y1 - y0 + 24);
  if (pts.length > 1) {
    let lo = Math.min(...pts), hi = Math.max(...pts);
    if (v.entry) { lo = Math.min(lo, v.entry); hi = Math.max(hi, v.entry); }
    const pad = Math.max((hi - lo) * .12, 8); lo -= pad; hi += pad;
    const X = i => x0 + i / (pts.length - 1) * (x1 - x0), Y = p => y1 - (p - lo) / (hi - lo) * (y1 - y0);
    ctx.strokeStyle = C.line; ctx.lineWidth = 1;
    for (let k = 1; k < 4; k++) { const y = y0 + (y1 - y0) * k / 4; ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke(); }
    const grad = ctx.createLinearGradient(0, y0, 0, y1); grad.addColorStop(0, 'rgba(173,159,248,.28)'); grad.addColorStop(1, 'rgba(173,159,248,0)');
    ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(X(i), Y(p)) : ctx.moveTo(X(i), Y(p)))); ctx.lineTo(x1, y1); ctx.lineTo(x0, y1); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
    ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(X(i), Y(p)) : ctx.moveTo(X(i), Y(p)))); ctx.strokeStyle = C.violet; ctx.lineWidth = 3.5; ctx.stroke();
    ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(X(pts.length - 1), Y(pts[pts.length - 1]), 6, 0, Math.PI * 2); ctx.fill();
    if (v.entry) dashed(ctx, x0, x1, Y(v.entry), v.side === 'LONG' ? C.long : C.short, `진입 ${num(v.entry, 1)}`, 'left');
    if (v.liq) {
      const y = Y(v.liq);
      if (y >= y0 && y <= y1) dashed(ctx, x0, x1, y, C.short, `청산가 ${num(v.liq, 1)}`);
      else { ctx.font = font(700, 18); ctx.fillStyle = C.short; ctx.textAlign = 'right'; ctx.fillText(`${y < y0 ? '▲' : '▼'} 청산가 ${num(v.liq, 1)}`, x1 - 6, y < y0 ? y0 + 16 : y1 - 8); }
    }
    ctx.font = font(500, 15); ctx.fillStyle = C.mute; ctx.textAlign = 'left'; ctx.fillText(`최근 ${pts.length}분`, x0 + 6, y1 + 30);
  } else { ctx.font = font(500, 20); ctx.fillStyle = C.mute; ctx.textAlign = 'center'; ctx.fillText('시세 대기 중…', (x0 + x1) / 2, (y0 + y1) / 2); }
  // The fly's eye: the actual 320×180 retina frame the brain received this observation.
  const ex = 836, ey = 96, ew = 404, eh = 227;
  ctx.fillStyle = C.panel; ctx.fillRect(ex - 6, ey - 6, ew + 12, eh + 46);
  if (v.eye && v.eye.complete && v.eye.naturalWidth) { ctx.imageSmoothingEnabled = false; ctx.drawImage(v.eye, ex, ey, ew, eh); ctx.imageSmoothingEnabled = true; }
  else { ctx.fillStyle = '#0d1422'; ctx.fillRect(ex, ey, ew, eh); }
  ctx.textAlign = 'left'; ctx.font = font(700, 18); ctx.fillStyle = C.gold; ctx.fillText('👁 초파리의 눈', ex, ey + eh + 30);
  ctx.font = font(500, 15); ctx.fillStyle = C.mute; ctx.fillText('뇌가 실제로 받은 입력', ex + 132, ey + eh + 29);
  // Position.
  const px = 836, py = 360;
  ctx.fillStyle = C.panel; ctx.fillRect(px - 6, py, 416, 208);
  ctx.font = font(500, 16); ctx.fillStyle = C.mute; ctx.fillText('포지션', px + 8, py + 30);
  if (v.side) {
    ctx.font = font(800, 40); ctx.fillStyle = v.side === 'LONG' ? C.long : C.short; ctx.fillText(v.side === 'LONG' ? '롱 20×' : '숏 20×', px + 8, py + 80);
    ctx.font = font(600, 20); ctx.fillStyle = C.text; ctx.fillText(`${num(v.qty, 3)} BTC @ ${num(v.entry, 1)}`, px + 8, py + 116);
    ctx.font = font(800, 30); ctx.fillStyle = v.upnl >= 0 ? C.long : C.short; ctx.fillText(`${signed(v.upnl)} USDT`, px + 8, py + 160);
    ctx.font = font(500, 16); ctx.fillStyle = C.mute; ctx.fillText(`미실현 · 증거금 대비 ${signed(v.upnlPct, 1)}%`, px + 8, py + 190);
  } else { ctx.font = font(800, 40); ctx.fillStyle = C.mute; ctx.fillText('없음', px + 8, py + 84); }
  // Decision line.
  ctx.fillStyle = '#0f1522'; ctx.fillRect(35, 600, W - 70, 132);
  ctx.textAlign = 'left'; ctx.font = font(700, 22); ctx.fillStyle = C.gold; ctx.fillText('🧠 이번 관측', 58, 640);
  ctx.font = font(600, 26); ctx.fillStyle = C.text; ctx.fillText(v.decision || '뉴런 발화 대기 중…', 58, 684);
  ctx.font = font(500, 19); ctx.fillStyle = C.mute; ctx.fillText(v.outcome || '', 58, 718);
  // Event overlay ("롱 진입!", "익절!", "강제청산").
  if (v.overlay) {
    const a = v.overlay.alpha;
    ctx.fillStyle = `rgba(6,8,14,${.72 * a})`; ctx.fillRect(0, 0, W, H);
    ctx.globalAlpha = a; ctx.textAlign = 'center'; ctx.font = font(900, 128); ctx.fillStyle = v.overlay.color; ctx.fillText(v.overlay.text, W / 2, H / 2 + 20);
    if (v.overlay.sub) { ctx.font = font(700, 38); ctx.fillStyle = C.text; ctx.fillText(v.overlay.sub, W / 2, H / 2 + 90); }
    ctx.globalAlpha = 1;
  }
  scr.tex.needsUpdate = true;
}

export function drawSeason(scr, v) {
  const { ctx } = scr, W = 1024, H = 614;
  ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
  ctx.textAlign = 'left'; ctx.font = font(800, 30); ctx.fillStyle = C.text; ctx.fillText('시즌 순자산', 34, 54);
  ctx.font = font(500, 17); ctx.fillStyle = C.mute; ctx.fillText('노란선: 초파리 · 회색선: BTC 단순 보유(시작 1,000)', 34, 84);
  const pts = v.season || [], x0 = 40, x1 = W - 40, y0 = 120, y1 = H - 60;
  if (pts.length > 1) {
    const eq = pts.map(p => p.equity), bench = pts.map(p => v.seedBid ? v.init * p.bid / v.seedBid : v.init);
    let lo = Math.min(...eq, ...bench, v.init), hi = Math.max(...eq, ...bench, v.init); const pad = (hi - lo) * .1 + 1; lo -= pad; hi += pad;
    const X = i => x0 + i / (pts.length - 1) * (x1 - x0), Y = e => y1 - (e - lo) / (hi - lo) * (y1 - y0);
    dashed(ctx, x0, x1, Y(v.init), '#4a5570', `시작 ${num(v.init, 0)}`, 'left');
    ctx.beginPath(); bench.forEach((e, i) => (i ? ctx.lineTo(X(i), Y(e)) : ctx.moveTo(X(i), Y(e)))); ctx.strokeStyle = '#6c7690'; ctx.lineWidth = 3; ctx.stroke();
    ctx.beginPath(); eq.forEach((e, i) => (i ? ctx.lineTo(X(i), Y(e)) : ctx.moveTo(X(i), Y(e)))); ctx.strokeStyle = C.gold; ctx.lineWidth = 5; ctx.stroke();
    pts.forEach((p, i) => { if (p.liq) { ctx.fillStyle = C.short; ctx.font = font(900, 26); ctx.textAlign = 'center'; ctx.fillText('×', X(i), Y(p.equity) + 9); } });
    ctx.textAlign = 'right'; ctx.font = font(800, 34); ctx.fillStyle = eq[eq.length - 1] >= v.init ? C.long : C.short;
    ctx.fillText(`${num(eq[eq.length - 1], 2)} USDT`, x1, 56);
  } else { ctx.font = font(500, 20); ctx.fillStyle = C.mute; ctx.textAlign = 'center'; ctx.fillText('기록 쌓는 중…', W / 2, H / 2); }
  scr.tex.needsUpdate = true;
}

export function drawStats(scr, v) {
  const { ctx } = scr, W = 1024, H = 614;
  ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
  ctx.textAlign = 'left'; ctx.font = font(800, 30); ctx.fillStyle = C.text; ctx.fillText('시즌 기록', 34, 54);
  const rows = [
    ['최고 순자산', `${num(v.best, 2)} USDT`, C.gold], ['실현 손익', `${signed(v.realized)} USDT`, v.realized >= 0 ? C.long : C.short],
    ['누적 수수료', `−${num(v.fees, 2)} USDT`, C.short], ['누적 펀딩', `${signed(-v.funding)} USDT`, -v.funding >= 0 ? C.long : C.short],
    ['강제청산', `${v.liquidations}회`, v.liquidations ? C.short : C.text], ['해금한 방 아이템', `${v.unlocked}/8`, C.violet],
  ];
  rows.forEach(([k, val, col], i) => {
    const y = 120 + i * 78;
    ctx.fillStyle = C.panel; ctx.fillRect(34, y - 44, W - 68, 64);
    ctx.font = font(500, 24); ctx.fillStyle = C.mute; ctx.textAlign = 'left'; ctx.fillText(k, 58, y);
    ctx.font = font(800, 30); ctx.fillStyle = col; ctx.textAlign = 'right'; ctx.fillText(val, W - 58, y + 2);
  });
  scr.tex.needsUpdate = true;
}

"""Apply the Korean UI strings to dashboard/index.html. Idempotent; run once per checkout."""

import sys
from pathlib import Path

REPLACEMENTS = [
    ('<html lang="zh-Hant">', '<html lang="ko">'),
    ("<title>Stonkfly 神經儀表板</title>", "<title>초파리 트레이딩 챌린지</title>"),
    ('px system-ui, sans-serif', 'px "Pretendard Variable", system-ui, sans-serif'),
    # header
    ('<span class="coin" translate="no">–</span> 果蠅</h1>', '<span class="coin" translate="no">–</span> <span id="flyName">초파리</span></h1>'),
    ('<span id="status" class="pill">載入中…</span>', '<span id="status" class="pill">불러오는 중…</span>'),
    ('title="這個網頁只讀取交易程式的紀錄，不能下單，也不能改任何狀態"><span aria-hidden="true">🔒</span> 唯讀</span>',
     'title="이 페이지는 러너 기록을 읽기만 합니다. 주문도, 상태 변경도 못 합니다"><span aria-hidden="true">🔒</span> 읽기 전용</span>'),
    ('<span class="stat">第 <strong id="tick">–</strong> 步</span>', '<span class="stat">D+<strong id="day">–</strong></span>\n  <span class="stat"><strong id="tick">–</strong>번째 관측</span>'),
    ('<span class="stat">模擬淨值 <strong id="equity">–</strong> USDC</span>', '<span class="stat">순자산 <strong id="equity">–</strong> USDT <strong id="roi">–</strong></span>\n  <span class="stat">오늘 매매 <strong id="tradesToday">–</strong></span>'),
    ('<span class="stat">下一步 <strong id="next">–</strong></span>', '<span class="stat">다음 관측 <strong id="next">–</strong></span>'),
    ('<span class="stat">本步模擬耗時 <strong id="compute">–</strong></span>', '<span class="stat">이번 관측 컴퓨트 <strong id="compute">–</strong></span>'),
    ('aria-label="切換到白天模式"><span aria-hidden="true">☀️</span> 白天模式</button>', 'aria-label="라이트 모드로 전환"><span aria-hidden="true">☀️</span> 라이트 모드</button>'),
    # flow strip
    ('<b>① 價格畫成圖</b>最近 100&nbsp;分鐘的 <span class="coin" translate="no">–</span> 走勢畫成 320×180 彩色圖', '<b>① 가격을 그림으로</b>최근 100&nbsp;분 <span class="coin" translate="no">–</span> 흐름을 320×180 컬러 차트로'),
    ('<b>② 眼睛看圖</b>3,335&nbsp;個感光細胞看亮度、811&nbsp;個看藍/綠色', '<b>② 눈이 본다</b>광수용체 3,335개가 밝기를, 811개가 파랑/초록을 봄'),
    ('<b>③ 神經傳遞 0.5&nbsp;秒</b>16.6&nbsp;萬神經元、2,560&nbsp;萬條真實連線，逐 0.1&nbsp;ms 模擬放電', '<b>③ 신경 전달 0.5&nbsp;초</b>뉴런 16.7만 개·실제 연결 2,558만 개를 0.1&nbsp;ms 단위로 발화 시뮬레이션'),
    ('<b>④ 讀出決策</b>比較左右兩顆 <span translate="no">DNp20</span> 的放電頻率，<span translate="no">DNpe017</span> 當閘門', '<b>④ 결정 읽기</b>좌우 <span translate="no">DNp20</span> 발화율을 비교, <span translate="no">DNpe017</span>이 게이트'),
    ('<b>⑤ 下單</b>買／賣／持有；風控只能否決，不能替牠換決定', '<b>⑤ 주문</b>롱／숏／관망. 리스크 가드는 거부만 할 뿐 결정을 바꾸지 못함'),
    ('<b>↺ 回饋學習</b>賺錢刺激 <span translate="no">PAM11</span> 多巴胺、虧錢刺激 <span translate="no">PPL101</span>，改變蕈狀體 <span translate="no">KC→MBON</span> 突觸強度', '<b>↺ 피드백 학습</b>수익이면 <span translate="no">PAM11</span> 도파민, 손실이면 <span translate="no">PPL101</span>을 자극해 버섯체 <span translate="no">KC→MBON</span> 시냅스 강도를 바꿈'),
    # brain card
    ('大腦＋腹神經索：放電即時動畫', '뇌＋복부신경삭: 실시간 발화 애니메이션'),
    ('每個點是一個神經元的細胞體位置（MaleCNS 實測座標）。每一步新資料進來時，訊號從眼睛依真實突觸距離一層層傳進大腦；之後每個神經元依上一步的實際頻率閃爍（慢動作 ×8）。拖曳或方向鍵旋轉、Ctrl＋滾輪或 ＋／－ 縮放、滑鼠移上去看是什麼神經元。',
     '점 하나가 뉴런 하나의 세포체 위치(MaleCNS 실측 좌표)입니다. 새 관측이 들어오면 신호가 눈에서 실제 시냅스 거리 순으로 뇌로 퍼지고, 그 뒤 각 뉴런은 직전 관측의 실제 발화율로 깜빡입니다(슬로모션 ×8). 드래그·방향키 회전, Ctrl＋휠 또는 ＋／－ 확대, 마우스를 올리면 뉴런 정보.'),
    ('aria-label="果蠅大腦與腹神經索的神經元放電動畫（方向鍵旋轉，＋／－縮放）"', 'aria-label="초파리 뇌와 복부신경삭 발화 애니메이션(방향키 회전, ＋／－ 확대)"'),
    ('title="只在瀏覽器重跑動畫，不會下單">▶ 重播動畫（不會下單）</button>', 'title="브라우저에서 애니메이션만 다시 재생합니다. 주문 없음">▶ 애니메이션 다시 보기(주문 없음)</button>'),
    ('aria-pressed="true">自動旋轉</button>', 'aria-pressed="true">자동 회전</button>'),
    ('<button id="bFront">正面</button>', '<button id="bFront">정면</button>'),
    ('<button id="bSide">側面</button>', '<button id="bSide">측면</button>'),
    ('<button id="bTop">俯視</button>', '<button id="bTop">위에서</button>'),
    ('aria-label="放大大腦視圖">＋</button>', 'aria-label="뇌 확대">＋</button>'),
    ('aria-label="縮小大腦視圖">－</button>', 'aria-label="뇌 축소">－</button>'),
    ('<button id="bMode">改成：依區域著色</button>', '<button id="bMode">바꾸기: 영역별 색</button>'),
    ('aria-pressed="false">顯示記憶細胞 KC</button>', 'aria-pressed="false">기억세포 KC 표시</button>'),
    ('aria-pressed="false">標出感光細胞</button>', 'aria-pressed="false">광수용체 표시</button>'),
    # eye card
    ('<span aria-hidden="true">👁</span> 果蠅的眼睛</h2>', '<span aria-hidden="true">👁</span> 초파리의 눈</h2>'),
    ('aria-label="果蠅眼睛：價格圖與每個感光細胞看到的亮度"', 'aria-label="초파리 눈: 가격 차트와 광수용체별 밝기"'),
    ('<button id="bEyeMode">改成：只看果蠅看到的</button>', '<button id="bEyeMode">바꾸기: 초파리가 본 것만</button>'),
    # decision card
    ('<span aria-hidden="true">🎯</span> 這一步的決策</h2>', '<span aria-hidden="true">🎯</span> 이번 관측의 결정</h2>'),
    ('<span>DNp20 左</span>', '<span>DNp20 좌</span>'),
    ('<span>DNp20 右</span>', '<span>DNp20 우</span>'),
    ('<span>右 − 左</span>', '<span>우 − 좌</span>'),
    ('<span>DNpe017 閘門</span>', '<span>DNpe017 게이트</span>'),
    ('規則（固定、人工設計）：閘門有放電，且 右−左 &gt; 2&nbsp;Hz → <b style="color:var(--buy)">買</b>；&lt; −2&nbsp;Hz → <b style="color:var(--sell)">賣</b>；其他 → 持有。',
     '규칙(고정, 사람이 설계): 게이트가 발화하고 우−좌 &gt; 2&nbsp;Hz → <b style="color:var(--buy)">롱</b>; &lt; −2&nbsp;Hz → <b style="color:var(--sell)">숏</b>; 그 외 → 관망.'),
    # dopamine card
    ('<span aria-hidden="true">💊</span> 回饋刺激</h2>', '<span aria-hidden="true">💊</span> 피드백 자극</h2>'),
    ('<span>PAM11 獎勵</span>', '<span>PAM11 보상</span>'),
    ('<span>PPL101 懲罰</span>', '<span>PPL101 처벌</span>'),
    ('<span>KC 記憶細胞</span>', '<span>KC 기억세포</span>'),
    # fly card
    ('<span aria-hidden="true">🪰</span> 果蠅交易員動畫 ', '<span aria-hidden="true">🪰</span> 초파리 트레이더 '),
    ('aria-label="暫停果蠅動畫">❚❚ 暫停</button>', 'aria-label="애니메이션 일시정지">❚❚ 일시정지</button>'),
    ('aria-label="四種動畫代表的狀態"', 'aria-label="애니메이션이 뜻하는 상태"'),
    ('<span aria-hidden="true">🚀</span> 買進成交</b><span>火箭登月</span>', '<span aria-hidden="true">🚀</span> 진입 체결</b><span>로켓 발사</span>'),
    ('<span aria-hidden="true">💸</span> 賣出賺錢</b><span>噴鈔派對</span>', '<span aria-hidden="true">💸</span> 익절 청산</b><span>돈다발 파티</span>'),
    ('<span aria-hidden="true">⛺</span> 賣出虧損</b><span>破帳篷躺地</span>', '<span aria-hidden="true">⛺</span> 손절·강제청산</b><span>텐트 붕괴</span>'),
    ('<span aria-hidden="true">🧼</span> 其他狀態</b><span>觀望、被風控擋下或停機時搓手洗臉</span>', '<span aria-hidden="true">🧼</span> 그 외</b><span>관망·거부·정지 중엔 그루밍</span>'),
    # charts
    ('<span class="coin" translate="no">–</span> 價格與模擬淨值</h2><p class="sub">藍線：<span class="coin" translate="no">–</span> 買價；黃線：模擬帳戶淨值（右軸）。▲ 買 ▼ 賣</p>',
     '<span class="coin" translate="no">–</span> 가격과 순자산</h2><p class="sub">파란선: <span class="coin" translate="no">–</span> 매수호가, 노란선: 페이퍼 순자산(오른쪽 축), 회색선: BTC 단순 보유(시즌 시작 대비, 1,000 USDT 환산). ▲ 롱 ▼ 숏 × 강제청산 ◇ 펀딩 ● 방 이벤트</p>'),
    ('左右 <span translate="no">DNp20</span> 放電差（Hz）</h2><p class="sub">虛線是 ±2&nbsp;Hz 門檻；點的顏色＝當步決策（灰點＝閘門沒開或差距不夠）</p>',
     '좌우 <span translate="no">DNp20</span> 발화 차이(Hz)</h2><p class="sub">점선은 ±2&nbsp;Hz 문턱. 점 색＝그 관측의 결정(회색＝게이트 안 열림 또는 차이 부족)</p>'),
    ('多巴胺放電</h2><p class="sub">綠：PAM11 獎勵；紅：PPL101 懲罰（受損益刺激時才會高）</p>', '도파민 발화</h2><p class="sub">초록: PAM11 보상, 빨강: PPL101 처벌(손익 자극이 있을 때만 높아짐)</p>'),
    ('記憶突觸變化</h2><p class="sub">紫線：已改變的 KC→MBON 突觸數（共 7,835&nbsp;條）；青線：平均強度（1＝原始）</p>', '기억 시냅스 변화</h2><p class="sub">보라선: 바뀐 KC→MBON 시냅스 수(총 7,835개), 청록선: 평균 강도(1＝원래)</p>'),
    ('各區域平均放電頻率</h2><p class="sub">上一步 0.5&nbsp;秒，每個神經元平均 Hz</p>', '영역별 평균 발화율</h2><p class="sub">직전 관측 0.5&nbsp;초, 뉴런당 평균 Hz</p>'),
    ('記憶突觸強度分佈</h2><p class="sub">7,835&nbsp;條 KC→MBON07/11 突觸；1.0＝原始強度，&lt;1＝被多巴胺削弱</p>', '기억 시냅스 강도 분포</h2><p class="sub">KC→MBON07/11 시냅스 7,835개. 1.0＝원래 강도, &lt;1＝도파민으로 약해짐</p>'),
    # footer
    ('資料：<span id="runpath"></span>（paper 模擬交易，唯讀）。每 4&nbsp;秒檢查一次，新的一步出來就播放動畫並更新。<br>',
     '데이터: <span id="runpath"></span> (페이퍼 트레이딩, 읽기 전용). 4&nbsp;초마다 확인해 새 관측이 나오면 애니메이션을 재생하고 갱신합니다.<br>'),
    ('動畫說明：程式每 0.5&nbsp;秒只記錄「每個神經元放了幾次電」，沒有記錄每次放電的時間。傳遞波的先後是依「離眼睛幾個突觸」排的示意；閃爍頻率是真實的上一步放電頻率（放慢 8&nbsp;倍）。<br>',
     '애니메이션 설명: 프로그램은 0.5&nbsp;초마다 "뉴런이 몇 번 발화했는지"만 기록하고 발화 시각은 기록하지 않습니다. 전파 순서는 "눈에서 몇 시냅스 거리인지"로 배열한 시각화이고, 깜빡임 빈도는 직전 관측의 실제 발화율입니다(8&nbsp;배 느리게).<br>'),
    ('注意：「買／賣神經元」與「賺錢／虧錢多巴胺」都是人為指定的介面；連線來自真實果蠅連接體，但神經動力學與學習規則未經生物驗證，也未證明能獲利。\n</p>',
     '주의: "롱/숏 뉴런"과 "수익/손실 도파민"은 사람이 정한 인터페이스입니다. 연결은 실제 초파리 커넥톰에서 왔지만 신경 동역학과 학습 규칙은 생물학적으로 검증되지 않았고, 수익성도 입증되지 않았습니다.\n</p>'),
    # The disclosure strip belongs INSIDE the 16:9 stage (spec §7.2 "항상 표시"): below the
    # footer it is off camera in every recording.
    ('</div>\n\n</div></div><!-- /stage -->', '</div>\n<p class="foot" id="disclosure"></p>\n</div></div><!-- /stage -->'),
    # superclass names
    ("ENS:'腸神經'", "ENS:'장신경'"), ("ascending_neuron:'上行神經元（身體→腦）'", "ascending_neuron:'상행 뉴런(몸→뇌)'"),
    ("cb_efferent:'中央腦傳出'", "cb_efferent:'중앙뇌 원심'"), ("cb_endocrine:'中央腦內分泌'", "cb_endocrine:'중앙뇌 내분비'"),
    ("cb_intrinsic:'中央腦內部'", "cb_intrinsic:'중앙뇌 내부'"), ("cb_motor:'腦運動神經'", "cb_motor:'뇌 운동뉴런'"),
    ("cb_sensory:'腦感覺神經'", "cb_sensory:'뇌 감각뉴런'"), ("descending_neuron:'下行神經元（腦→身體）'", "descending_neuron:'하행 뉴런(뇌→몸)'"),
    ("efferent_ascending:'傳出上行'", "efferent_ascending:'원심 상행'"), ("efferent_descending:'傳出下行'", "efferent_descending:'원심 하행'"),
    ("ol_intrinsic:'視葉內部'", "ol_intrinsic:'시엽 내부'"), ("ol_sensory:'眼睛感光細胞'", "ol_sensory:'눈 광수용체'"),
    ("sensory_ascending:'感覺上行'", "sensory_ascending:'감각 상행'"), ("sensory_descending:'感覺下行'", "sensory_descending:'감각 하행'"),
    ("visual_centrifugal:'視覺離心'", "visual_centrifugal:'시각 원심'"), ("visual_projection:'視覺投射（眼→腦）'", "visual_projection:'시각 투사(눈→뇌)'"),
    ("vnc_efferent:'腹神經索傳出'", "vnc_efferent:'복부신경삭 원심'"), ("vnc_endocrine:'腹神經索內分泌'", "vnc_endocrine:'복부신경삭 내분비'"),
    ("vnc_intrinsic:'腹神經索內部'", "vnc_intrinsic:'복부신경삭 내부'"), ("vnc_motor:'腹神經索運動'", "vnc_motor:'복부신경삭 운동'"),
    ("vnc_sensory:'腹神經索感覺'", "vnc_sensory:'복부신경삭 감각'"), ("vnc_tbc:'腹神經索（待確認）'", "vnc_tbc:'복부신경삭(미확인)'"),
    ("unassigned:'未分類'", "unassigned:'미분류'"),
    ("+ '（待確認）' : s);", "+ '(미확인)' : s);"),
    ("{name:'視覺系統', color:[60,200,255]}", "{name:'시각계', color:[60,200,255]}"),
    ("{name:'中央腦', color:[169,139,255]}", "{name:'중앙뇌', color:[169,139,255]}"),
    ("{name:'腹神經索（身體）', color:[255,179,71]}", "{name:'복부신경삭(몸)', color:[255,179,71]}"),
    ("{name:'上行／下行', color:[255,122,184]}", "{name:'상행／하행', color:[255,122,184]}"),
    # execution / reasons / sides
    ("const EXEC = {FILLED:'已成交（模擬）', VETO:'風控否決', HOLD:'未下單', REJECTED:'被拒'};",
     "const EXEC = {FILLED:'체결(페이퍼)', VETO:'가드 거부', HOLD:'주문 없음', REJECTED:'거절', BANKRUPT:'파산'};"),
    ("'Price moved beyond neural observation tolerance':'神經運算期間價格變動超過容許範圍',",
     "'Price moved beyond neural observation tolerance':'신경 계산 중 가격이 허용 범위를 벗어남', 'Already positioned':'이미 같은 방향 포지션', 'Below breakeven':'수수료 보합 미만 — 보유 유지', 'Below minimum':'최소 주문 미만', 'Stale or future quote':'시세 지연', 'STOP file present':'STOP 파일', 'Incomplete market snapshot':'시세 불완전', 'Invalid neural proposal':'잘못된 제안', 'market-outage':'시세 장애', 'bankrupt':'파산', 'accounting-error':'회계 오류', 'clock-skew':'시계 어긋남 — 점검 필요', 'Checkpoint integrity':'체크포인트 무결성 오류 — 점검 필요', 'Quote identity mismatch':'시세 종목 불일치', 'SeedUnavailable':'초기 차트 시드 실패',"),
    ("'Order cooldown':'下單冷卻中（兩單至少間隔 60&nbsp;秒）',", "'Order cooldown':'주문 쿨다운(두 주문 사이 최소 60&nbsp;초)',"),
    ("'Insufficient funds/position or below exchange minimum':'資金或持倉不足／低於交易所最小單位',", "'Insufficient funds/position or below exchange minimum':'자금·포지션 부족 또는 거래소 최소 단위 미만',"),
    ("'Daily order limit':'已達每日下單上限', 'Spread limit':'買賣價差過大', 'Loss stop reached':'已達虧損停止線'", "'Daily order limit':'일일 주문 상한', 'Spread limit':'호가 스프레드 과대', 'Loss stop reached':'손실 정지선 도달'"),
    ("const SIDE_ZH = {BUY:'買 BUY', SELL:'賣 SELL', HOLD:'持有 HOLD'};", "const SIDE_ZH = {BUY:'롱 LONG', SELL:'숏 SHORT', HOLD:'관망 HOLD'};"),
    ("const STAGES = ['① 眼睛感光細胞看到價格圖', '② 視葉第一層（lamina）', '③ 視葉深層與視覺投射', '④ 中央腦與記憶中樞', '⑤ 遠端：腹神經索', '⑤ 遠端：腹神經索'];",
     "const STAGES = ['① 광수용체가 가격 차트를 봄', '② 시엽 첫 층(라미나)', '③ 시엽 심층과 시각 투사', '④ 중앙뇌와 기억 중추', '⑤ 원위: 복부신경삭', '⑤ 원위: 복부신경삭'];"),
    # legend
    ('`<span><i style="background:#ffe08a;box-shadow:0 0 6px #ffd166"></i>放電中</span>`', '`<span><i style="background:#ffe08a;box-shadow:0 0 6px #ffd166"></i>발화 중</span>`'),
    ('`<span><i style="background:var(--sell)"></i>DNp20 左（賣）</span><span><i style="background:var(--buy)"></i>DNp20 右（買）</span>`', '`<span><i style="background:var(--sell)"></i>DNp20 좌(숏)</span><span><i style="background:var(--buy)"></i>DNp20 우(롱)</span>`'),
    ('`<span><i style="background:var(--hot)"></i>DNpe017 閘門</span>`', '`<span><i style="background:var(--hot)"></i>DNpe017 게이트</span>`'),
    ('`<span><i style="border:2px solid var(--buy);background:none"></i>PAM11 獎勵多巴胺</span>`', '`<span><i style="border:2px solid var(--buy);background:none"></i>PAM11 보상 도파민</span>`'),
    ('`<span><i style="border:2px solid var(--sell);background:none"></i>PPL101 懲罰多巴胺</span>`', '`<span><i style="border:2px solid var(--sell);background:none"></i>PPL101 처벌 도파민</span>`'),
    # toasts in startWave / fireDecision
    ("? `<b>💊 獎勵刺激</b><br>上一步賺了 ${e.pnl.toFixed(4)} USDC → 刺激 15 顆 PAM11 多巴胺 200 ms`", "? `<b>💊 보상 자극</b><br>직전 관측 +${e.pnl.toFixed(2)} USDT → PAM11 도파민 15개 200 ms 자극`"),
    (": `<b>💊 懲罰刺激</b><br>上一步虧了 ${Math.abs(e.pnl).toFixed(4)} USDC → 刺激 2 顆 PPL101 多巴胺 200 ms`, e.stimulus);", ": `<b>💊 처벌 자극</b><br>직전 관측 −${Math.abs(e.pnl).toFixed(2)} USDT → PPL101 도파민 2개 200 ms 자극`, e.stimulus);"),
    ("sub: (wave.replay ? `⟲ 重播第 ${e.tick} 步 · 當時` : '') + (EXEC[e.execution] || e.execution)};", "sub: (wave.replay ? `↺ ${e.tick}번째 관측 다시 보기 · 당시` : '') + (EXEC[e.execution] || e.execution)};"),
    ("if (e.execution === 'FILLED') toast(`<b>${e.side === 'BUY' ? '🟢 買入成交' : '🔴 賣出成交'}</b>（模擬）<br>${e.product.split('-')[0]} @ ${fmtPrice(+e.bid)}　右−左 ${e.diff_hz >= 0 ? '+' : ''}${e.diff_hz.toFixed(0)} Hz`, e.side);",
     "if (e.execution === 'FILLED') toast(`<b>${e.action === 'FLIP' ? '🔁 뒤집기 → ' + (e.side === 'BUY' ? '롱' : '숏') : (e.side === 'BUY' ? '🟢 롱 진입' : '🔴 숏 진입')}</b>(페이퍼)<br>${e.product.split('-')[0]} @ ${fmtPrice(+e.bid)}　우−좌 ${e.diff_hz >= 0 ? '+' : ''}${e.diff_hz.toFixed(0)} Hz`, e.side);"),
    ("else if (e.execution === 'VETO') toast(`<b>🛡 神經想${e.side === 'BUY' ? '買' : '賣'}，被風控否決</b>${why}`, 'veto');", "else if (e.execution === 'VETO') toast(`<b>🛡 초파리는 ${e.side === 'BUY' ? '롱' : '숏'}을 원했지만 가드가 거부</b>${why}`, 'veto');"),
    ("else toast(`<b>⏸ 持有</b><br>右−左 ${e.diff_hz >= 0 ? '+' : ''}${e.diff_hz.toFixed(1)} Hz，閘門 ${e.gate} 次${e.gate ? '' : '（閘門沒開）'}`, 'HOLD');", "else toast(`<b>⏸ 관망</b><br>우−좌 ${e.diff_hz >= 0 ? '+' : ''}${e.diff_hz.toFixed(1)} Hz, 게이트 ${e.gate}회${e.gate ? '' : '(게이트 안 열림)'}`, 'HOLD');"),
    # overlay labels
    ("lab.push([SX[i], SY[i], `${text} ${COUNTS ? COUNTS[i] : 0} 次`, col]);", "lab.push([SX[i], SY[i], `${text} ${COUNTS ? COUNTS[i] : 0}회`, col]);"),
    ("big(g.dnp20_L, '#ff5d6c', 'DNp20左'); big(g.dnp20_R, '#2fd18a', 'DNp20右'); big(g.gate, '#ffd166', '閘門');", "big(g.dnp20_L, '#ff5d6c', 'DNp20 좌'); big(g.dnp20_R, '#2fd18a', 'DNp20 우'); big(g.gate, '#ffd166', '게이트');"),
    ("'PAM11 獎勵', '#2fd18a']);", "'PAM11 보상', '#2fd18a']);"),
    ("'PPL101 懲罰', '#ff5d6c']);", "'PPL101 처벌', '#ff5d6c']);"),
    ("'MBON 記憶輸出', '#c9b8ff']);", "'MBON 기억 출력', '#c9b8ff']);"),
    ("stage = '⑥ 0.5 秒結束 → 決策：' + SIDE_ZH[wave.event.side]; prog = 1;", "stage = '⑥ 0.5초 종료 → 결정: ' + sideLabel(wave.event); prog = 1;"),
    ("} else { stage = '等待下一步…神經元依上一步的頻率持續放電'; prog = null; }", "} else { stage = '다음 관측 대기 중… 뉴런은 직전 발화율로 계속 발화'; prog = null; }"),
    ("octx.fillText(`放電 ${wave.spikes.toLocaleString()} / ${wave.total.toLocaleString()} 次`, 20*P, 47*P);", "octx.fillText(`발화 ${wave.spikes.toLocaleString()} / ${wave.total.toLocaleString()}회`, 20*P, 47*P);"),
    ("octx.fillText('慢動作 ×8 · 傳遞順序依突觸距離（示意）', W - 10*P, H - 8*P);", "octx.fillText('슬로모션 ×8 · 전파 순서는 시냅스 거리(시각화)', W - 10*P, H - 8*P);"),
    ("const s = `⟲ 重播第 ${wave.event.tick} 步 · 僅動畫，不會下單`, w = octx.measureText(s).width + 16*P;", "const s = `↺ ${wave.event.tick}번째 관측 다시 보기 · 애니메이션만, 주문 없음`, w = octx.measureText(s).width + 16*P;"),
    ("octx.fillText(fx.stim === 'reward' ? '💊 獎勵多巴胺注入中' : '💊 懲罰多巴胺注入中', 14*P, H - 10*P);", "octx.fillText(fx.stim === 'reward' ? '💊 보상 도파민 주입 중' : '💊 처벌 도파민 주입 중', 14*P, H - 10*P);"),
    ("ty = META.type_names[TYPE[best]] || '（未命名類型）', h = HOP[best];", "ty = META.type_names[TYPE[best]] || '(이름 없는 유형)', h = HOP[best];"),
    ("<br>上一步放電 <b>${c}</b> 次（${(c / N_MS).toFixed(0)} Hz）` +", "<br>직전 관측 발화 <b>${c}</b>회(${(c / N_MS).toFixed(0)} Hz)` +"),
    ("`<br>離眼睛 ${h === 255 ? '無路徑' : h + ' 個突觸'}`;", "`<br>눈에서 ${h === 255 ? '경로 없음' : h + ' 시냅스'}`;"),
    ("$('#bMode').textContent = brain.mode === 'activity' ? '改成：依區域著色' : '改成：顯示放電'; };", "$('#bMode').textContent = brain.mode === 'activity' ? '바꾸기: 영역별 색' : '바꾸기: 발화 표시'; };"),
    # charts
    ("$(el).innerHTML = '<p class=\"sub\">等待資料…</p>'; return; }", "$(el).innerHTML = '<p class=\"sub\">데이터 대기 중…</p>'; return; }"),
    ('y="${H - 5}">第 ${opt.ticks[0]} 步</text>', 'y="${H - 5}">${opt.ticks[0]}번째</text>'),
    ('text-anchor="end">第 ${opt.ticks[1]} 步</text>', 'text-anchor="end">${opt.ticks[1]}번째</text>'),
    ("<title>${ed[i]}–${ed[i + 1]}：${v} 條</title>", "<title>${ed[i]}–${ed[i + 1]}: ${v}개</title>"),
    ('s += `<text class="axis" x="30" y="12">條數（對數刻度）</text>`;', 's += `<text class="axis" x="30" y="12">개수(로그 눈금)</text>`;'),
    ("`<span title=\"${r.s}，${r.size.toLocaleString()} 個神經元\">", "`<span title=\"${r.s}, 뉴런 ${r.size.toLocaleString()}개\">"),
    ("html = `<span style=\"color:var(--amber)\">⟲ 重播第 ${wave.event.tick} 步（僅動畫，不會下單）</span><br>` + html;", "html = `<span style=\"color:var(--amber)\">↺ ${wave.event.tick}번째 관측 다시 보기(애니메이션만, 주문 없음)</span><br>` + html;"),
    # drawPanels
    ("document.title = `Stonkfly ${coin} 果蠅`;", "document.title = `초파리 트레이딩 챌린지 · ${coin}`;"),
    ("$('#compute').textContent = e.compute.toFixed(1) + ' 秒';", "$('#compute').textContent = e.compute.toFixed(1) + '초';"),
    ("$('#side').textContent = SIDE_ZH[e.side]; $('#side').className", "$('#side').textContent = sideLabel(e); $('#side').className"),
    ("$('#exec').innerHTML = `執行：<strong", "$('#exec').innerHTML = `실행: <strong"),
    ("`<br>現金 ${(+lg.cash || 0).toFixed(2)} USDC` + (lg.positions && Object.keys(lg.positions).length ? `，持有 ${Object.entries(lg.positions).map(([k, v]) => `${fmtQty(+v)} ${k.split('-')[0]}`).join('、')}` : '');",
     "`<br>현금 ${(+lg.cash || 0).toFixed(2)} USDT` + (lg.position ? `, ${lg.position.side === 'LONG' ? '롱' : '숏'} ${fmtQty(+lg.position.qty)} BTC` : '');"),
    ("$('#numG').textContent = e.gate + ' 次';", "$('#numG').textContent = e.gate + '회';"),
    ("const st = {reward:'✅ 上一步賺錢 → 刺激 PAM11 獎勵多巴胺 200&nbsp;ms', aversive:'⚠️ 上一步虧錢 → 刺激 PPL101 懲罰多巴胺 200&nbsp;ms', none:'損益在 ±0.01&nbsp;USDC 內 → 沒有刺激'}[e.stimulus];",
     "const st = {reward:'✅ 이번 관측 수익 → PAM11 보상 도파민 200&nbsp;ms 자극', aversive:'⚠️ 이번 관측 손실 → PPL101 처벌 도파민 200&nbsp;ms 자극', none:'손익이 ±1&nbsp;USDT 안 → 자극 없음'}[e.stimulus];"),
    ("$('#reinf').innerHTML = `${st}<br>本步損益 ${e.pnl >= 0 ? '+' : ''}${e.pnl.toFixed(4)} USDC（含手續費）`;", "$('#reinf').innerHTML = `${st}<br>이번 관측 손익 ${e.pnl >= 0 ? '+' : '−'}${Math.abs(e.pnl).toFixed(2)} USDT(수수료·펀딩 포함)`;"),
    ("$('#numRw').textContent = e.reward_spikes + ' 次'; $('#numAv').textContent = e.aversive_spikes + ' 次'; $('#numKC').textContent = e.kc_spikes.toLocaleString() + ' 次';",
     "$('#numRw').textContent = e.reward_spikes + '회'; $('#numAv').textContent = e.aversive_spikes + '회'; $('#numKC').textContent = e.kc_spikes.toLocaleString() + '회';"),
    ("$('#status').textContent = STATE.stopped ? '已停止（STOP）' : lg.halted ? '已暫停：' + lg.halted : running ? (lg.mode === 'live' ? '運行中 · LIVE 真實下單' : '運行中 · paper 模擬') : '可能已停止';",
     "$('#status').textContent = STATE.stopped ? '정지됨(STOP)' : lg.halted ? (lg.halted === 'bankrupt' ? '파산 — 챌린지 종료' : '일시정지: ' + (REASON[lg.halted] || lg.halted)) : running ? (lg.mode === 'live' ? '실행 중 · LIVE 실주문' : '실행 중 · 페이퍼') : '정지된 듯';"),
    ("const clipName = {buy: '火箭登月', sell_profit: '噴鈔派對', sell_loss: '破帳篷躺地', hold: '搓手洗臉'}[anim];", "const clipName = {buy: '로켓 발사', sell_profit: '돈다발 파티', sell_loss: '텐트 붕괴', hold: '그루밍'}[anim];"),
    ("const clipWhy = anim !== 'hold' ? '' : !running ? '果蠅停機' : e.execution === 'VETO' ? '被風控擋下' : '觀望';", "const clipWhy = e.execution === 'BANKRUPT' ? '파산' : anim !== 'hold' ? '' : !running ? '초파리 정지' : e.execution === 'VETO' ? '가드 거부' : '관망';"),
    ("const nowText = '正在播：' + clipName + (clipWhy ? '（' + clipWhy + '）' : '');", "const nowText = '재생 중: ' + clipName + (clipWhy ? '(' + clipWhy + ')' : '');"),
    ("$('#eyeSub').textContent = eye.only ? '果蠅實際「看到」的：每個點是一個感光細胞，白點看亮度（R1–R6），藍／綠點看顏色（R8）。' : '輸入的價格圖（半透明）＋每個感光細胞「看」的位置，亮度＝牠感受到的光。新的一步進來時會從左到右掃描。';",
     "$('#eyeSub').textContent = eye.only ? '초파리가 실제로 \"본\" 것: 점 하나가 광수용체 하나, 흰 점은 밝기(R1–R6), 파랑/초록 점은 색(R8).' : '입력 가격 차트(반투명)＋각 광수용체가 \"보는\" 위치, 밝기＝느낀 빛. 새 관측이 오면 왼쪽에서 오른쪽으로 스캔.';"),
    ("$('#next').textContent = left > 0 ? `${left} 秒後` : '運算中…';", "$('#next').textContent = left > 0 ? `${left}초 후` : '계산 중…';"),
    ("b.setAttribute('aria-label', p ? '播放果蠅動畫' : '暫停果蠅動畫');", "b.setAttribute('aria-label', p ? '애니메이션 재생' : '애니메이션 일시정지');"),
    ("b.textContent = p ? '▶ 播放' : '❚❚ 暫停';", "b.textContent = p ? '▶ 재생' : '❚❚ 일시정지';"),
    ("b.innerHTML = light ? '<span aria-hidden=\"true\">🌙</span> 黑夜模式' : '<span aria-hidden=\"true\">☀️</span> 白天模式';", "b.innerHTML = light ? '<span aria-hidden=\"true\">🌙</span> 다크 모드' : '<span aria-hidden=\"true\">☀️</span> 라이트 모드';"),
    ("b.setAttribute('aria-label', light ? '切換到黑夜模式' : '切換到白天模式');", "b.setAttribute('aria-label', light ? '다크 모드로 전환' : '라이트 모드로 전환');"),
    ("$('#status').textContent = '連不到伺服器，4 秒後自動重試…';", "$('#status').textContent = '서버 연결 실패, 4초 후 재시도…';"),
    ("$('#bEyeMode').textContent = eye.only ? '改成：疊在原圖上' : '改成：只看果蠅看到的';", "$('#bEyeMode').textContent = eye.only ? '바꾸기: 원본 위에 겹쳐 보기' : '바꾸기: 초파리가 본 것만';"),
]


def apply(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    n = 0
    for old, new in REPLACEMENTS:
        if old in text:
            text = text.replace(old, new)
            n += 1
    path.write_text(text, encoding="utf-8")
    return n


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "dashboard" / "index.html"
    print(f"applied {apply(target)} replacements to {target}")

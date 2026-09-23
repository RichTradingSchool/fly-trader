"""Stonkfly live neural dashboard (read-only).

Reads the checkpoints, events and ledger that `python -m stonkfly run` writes into
a run directory and serves them to index.html. It never writes to the run and
refuses every non-GET request.

Usage (from the repository root):
    python dashboard/server.py [RUN_DIR]        # default: runs/paper

Environment variables: see README.md ("Dashboard configuration").
"""

import gzip
import hashlib
import json
import re
import os
import sqlite3
from decimal import Decimal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import numpy as np

HERE = Path(__file__).resolve().parent
# Repository root (the directory that contains the `stonkfly` package and `data/`).
ROOT = Path(os.environ.get("STONKFLY_ROOT", HERE.parent)).resolve()
RUN = Path(
    sys.argv[1] if len(sys.argv) > 1 else os.environ.get("STONKFLY_RUN", ROOT / "runs/paper")
).resolve()
PORT = int(os.environ.get("PORT", "8765"))
# Localhost by default. Set HOST=0.0.0.0 to open it to your LAN (read-only, no auth).
HOST = os.environ.get("HOST", "127.0.0.1")
CACHE = Path(os.environ.get("STONKFLY_VIZ_CACHE", HERE / "cache"))
ANIM_DIR = Path(os.environ.get("STONKFLY_ANIM", HERE / "anim"))
# Optional links to other dashboards, e.g. "BTC fly:8765,PEPE fly:8766".
FLIES = [
    {"name": name.strip(), "port": int(port)}
    for name, _, port in (
        item.rpartition(":") for item in os.environ.get("STONKFLY_FLIES", "").split(",") if item.strip()
    )
]
os.environ.setdefault("STONKFLY_DATA", str(ROOT / "data"))
DATA = Path(os.environ["STONKFLY_DATA"])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from perp_state import (  # noqa: E402
    fills_today, fly_name, perp_events, perp_ledger, perp_settings, perp_trade_pnl,
    room_recent, season_series, tail_lines, venue_of, veto_count,
)
from live_feed import current_tick, live_payload  # noqa: E402

# "Today" on the top strip is the viewer's day. Default KST (UTC+9).
try:
    TZ_OFFSET = int(os.environ.get("DASH_TZ_OFFSET", "32400"))
except ValueError:
    TZ_OFFSET = 32400

DISCLOSURE = [
    "페이퍼 트레이딩 · 실거래 없음 · 투자 자문 아님",
    "매매 규칙은 제작자가 설계했고 초파리 뇌는 신호만 만든다",
    "60초 관측이라 봉 내 순간 청산은 반영되지 않는다",
    "시세: OrangeX BTC 무기한(공개 API), 초기 차트 시드: Bybit 1분봉",
    "데이터: MaleCNS v1.0 CC BY 4.0 (FlyEM/HHMI Janelia, Univ. Cambridge, MRC LMB, Google Research; Berg et al., Cell 189(18), 2026) · 엔진: Stonkfly (Alex Wormuth, MIT) · 대시보드: Bgihe (MIT) · 초파리 모델: Degeneret Fly (Robillionair OÜ, MIT)",
]
FONT_DIR = HERE / "assets" / "fonts"
MILESTONES = ROOT / "stonkfly" / "perp" / "milestones.json"
# The 3D live studio (/room): three.js scene, vendored three.js, no external requests.
ROOM_DIR = HERE / "room"
ROOM_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".txt": "text/plain; charset=utf-8"}


def build_static():
    """Neuron positions, superclasses and identified groups; cached on disk."""
    if (CACHE / "static.npz").exists() and (CACHE / "meta.json").exists():
        z = np.load(CACHE / "static.npz")
        return z["pos"], z["sc"], z["type"], json.loads((CACHE / "meta.json").read_text())
    import pyarrow.feather as feather

    from stonkfly.neural.visual import projection

    g = np.load(DATA / "graph.npz")
    ids, ptr, post, retina = g["ids"], g["ptr"], g["post"], g["retina"]
    n = len(ids)
    cols = [
        "bodyId", "type", "superclass", "somaSide", "rootSide",
        "somaLocation", "tosomaLocation", "assignedOlHex1", "assignedOlHex2",
    ]
    a = (
        feather.read_table(DATA / "annotations.feather", columns=cols)
        .to_pandas()
        .set_index("bodyId")
        .loc[ids]
    )
    pos = np.full((n, 3), np.nan, dtype=np.float64)
    for col in ["somaLocation", "tosomaLocation"]:
        values = a[col].to_numpy()
        for i in np.flatnonzero(np.isnan(pos[:, 0])):
            v = values[i]
            if isinstance(v, (list, tuple, np.ndarray)) and len(v) == 3:
                pos[i] = v
    measured = ~np.isnan(pos[:, 0])
    # Cells without a soma in the volume (e.g. photoreceptors) are placed at
    # the mean position of their synaptic partners. Display only.
    src = np.repeat(np.arange(n, dtype=np.int32), np.diff(ptr))
    for _ in range(4):
        miss = np.isnan(pos[:, 0])
        if not miss.any():
            break
        known = ~miss
        acc = np.zeros((n, 3))
        out_e = miss[src] & known[post]
        in_e = miss[post] & known[src]
        cnt = np.bincount(src[out_e], minlength=n) + np.bincount(post[in_e], minlength=n)
        for k in range(3):
            acc[:, k] = np.bincount(
                src[out_e], weights=pos[post[out_e], k], minlength=n
            ) + np.bincount(post[in_e], weights=pos[src[in_e], k], minlength=n)
        fill = miss & (cnt > 0)
        pos[fill] = acc[fill] / cnt[fill, None]
    del src

    superclass = a.superclass.fillna("unassigned").astype(str).to_numpy()
    names, sc = np.unique(superclass, return_inverse=True)
    t = a.type.fillna("").astype(str).to_numpy(dtype=str)
    side = a.somaSide.fillna("").astype(str).to_numpy(dtype=str)
    type_names, type_code = np.unique(t, return_inverse=True)

    def idx(mask):
        return np.flatnonzero(mask).tolist()

    brain = SimpleNamespace(ptr=ptr, post=post, weight=g["weight"], retina=retina)
    r8, r8_uv, _ = projection(brain, a)
    groups = {
        "dnp20_L": idx((t == "DNp20") & (side == "L")),
        "dnp20_R": idx((t == "DNp20") & (side == "R")),
        "gate": idx(t == "DNpe017"),
        "reward": idx(t == "PAM11"),
        "aversive": idx(t == "PPL101"),
        "mbon": idx(np.isin(t, ["MBON07", "MBON11"])),
        "kc": idx(np.char.startswith(t, "KC")),
        "retina": retina.tolist(),
        "r8": r8.tolist(),
    }
    meta = {
        "n": n,
        "superclasses": names.tolist(),
        "superclass_sizes": np.bincount(sc, minlength=len(names)).tolist(),
        "type_names": type_names.tolist(),
        "groups": groups,
        "retina_uv": np.round(g["uv"], 4).tolist(),
        "r8_uv": np.round(r8_uv, 4).tolist(),
        "r8_channel": np.where(a.type.iloc[r8].eq("R8p"), 2, 1).tolist(),
        "measured_positions": int(measured.sum()),
        "inferred_positions": int((~measured & ~np.isnan(pos[:, 0])).sum()),
        "unplaced": int(np.isnan(pos[:, 0]).sum()),
        "bounds_min": np.nanmin(pos, axis=0).tolist(),
        "bounds_max": np.nanmax(pos, axis=0).tolist(),
    }
    pos = pos.astype(np.float32)
    sc = sc.astype(np.uint8)
    type_code = type_code.astype(np.uint16)
    CACHE.mkdir(exist_ok=True)
    np.savez(CACHE / "static.npz", pos=pos, sc=sc, type=type_code)
    (CACHE / "meta.json").write_text(json.dumps(meta))
    return pos, sc, type_code, meta


def hop_distance():
    """Synaptic hops from the photoreceptors (R1-R6 and R8). 255 = unreachable."""
    path = CACHE / "hop.npy"
    if path.exists():
        return np.load(path)
    g = np.load(DATA / "graph.npz")
    ptr, post = g["ptr"], g["post"]
    n = len(ptr) - 1
    src = np.repeat(np.arange(n, dtype=np.int32), np.diff(ptr))
    hop = np.full(n, 255, dtype=np.uint8)
    seeds = np.r_[g["retina"], np.asarray(META["groups"]["r8"], dtype=np.int32)]
    hop[seeds] = 0
    frontier = hop == 0
    level = 0
    while frontier.any() and level < 254:
        level += 1
        reached = np.zeros(n, dtype=bool)
        reached[post[frontier[src]]] = True
        reached &= hop == 255
        hop[reached] = level
        frontier = reached
    np.save(path, hop)
    return hop


POS, SC, TYPE, META = build_static()
HOP = hop_distance()
_checkpoint = {"key": None}
# The static brain files never change while the server runs: serialize and compress them once.
STATIC_BODIES = {
    "/meta.json": (json.dumps(META).encode(), "application/json"),
    "/pos.bin": (POS.tobytes(), "application/octet-stream"),
    "/sc.bin": (SC.tobytes(), "application/octet-stream"),
    "/hop.bin": (HOP.tobytes(), "application/octet-stream"),
    "/type.bin": (TYPE.tobytes(), "application/octet-stream"),
}
_GZ = {}
_GZ_LOCK = threading.Lock()


def gz_static(route):
    with _GZ_LOCK:
        if route not in _GZ:
            _GZ[route] = gzip.compress(STATIC_BODIES[route][0], 6)
        return _GZ[route]


def checkpoint():
    files = sorted(RUN.glob("brain-*.npz"), key=lambda p: p.stat().st_mtime_ns)
    if not files:
        return None
    key = (str(files[-1]), files[-1].stat().st_mtime_ns)
    if _checkpoint["key"] != key:
        with np.load(files[-1], allow_pickle=False) as z:
            meta = json.loads(str(z["metadata"]))
            efficacy = 1 + z["memory_w"]
            hist, edges = np.histogram(efficacy, bins=40, range=(0.1, 2.0))
            _checkpoint.update(
                key=key,
                counts=np.minimum(z["counts"], 255).astype(np.uint8).tobytes(),
                luminance=np.round(z["luminance"], 3).tolist(),
                r8_light=np.round(z["r8_light"], 3).tolist(),
                efficacy_hist=hist.tolist(),
                efficacy_edges=np.round(edges, 3).tolist(),
                brain_ms=meta["cursor"] * 0.1,
                mtime=files[-1].stat().st_mtime,
            )
    return _checkpoint


def ledger():
    try:
        db = sqlite3.connect(f"file:{RUN / 'ledger.sqlite'}?mode=ro", uri=True)
        meta = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM meta")}
        db.close()
        return {
            k: meta.get(k)
            for k in ["mode", "venue", "tick", "cash", "positions", "initial_cash", "halted"]
        }
    except sqlite3.Error:
        return {}


def trade_pnl():
    """Realized P&L of every settled SELL, keyed by its fill, on average cost."""
    out = {}
    try:
        db = sqlite3.connect(f"file:{RUN / 'ledger.sqlite'}?mode=ro", uri=True)
        rows = db.execute(
            "SELECT plan, settlement FROM orders"
            " WHERE status='SETTLED' AND settlement IS NOT NULL ORDER BY created"
        ).fetchall()
        db.close()
    except sqlite3.Error:
        return out
    held = {}
    for plan, settlement in rows:
        p, s = json.loads(plan), json.loads(settlement)
        base, quote, fee = Decimal(s["base"]), Decimal(s["quote"]), Decimal(s["fee"])
        qty, cost = held.get(p["product"], (Decimal(0), Decimal(0)))
        if p["side"] == "BUY":
            held[p["product"]] = (qty + base, cost + quote + fee)
        elif qty > 0:
            sold = min(base, qty)
            basis = cost * sold / qty
            out[f"{s['base']}|{s['quote']}"] = float(quote - fee - basis)
            held[p["product"]] = (qty - sold, cost - basis)
    return out


def state():
    # The venue comes from provenance.json (written before the first tick), not from
    # the ledger: a transient sqlite read failure must not silently switch a perpetual
    # run to the spot code path, which then crashes on the perpetual's skip rows.
    perp = venue_of(RUN) == "orangex-perp"
    lg = perp_ledger(RUN) if perp else ledger()
    events = []
    vetoes = 0
    room = {"unlocked": [], "events": []}
    season = {"seed_bid": None, "points": []}
    path = RUN / "events.jsonl"
    if path.exists():
        lines = tail_lines(path, 400)
        if perp:
            events = perp_events(lines, perp_trade_pnl(RUN))
            vetoes = veto_count(lines)
            room = {"unlocked": lg.get("room_unlocked") or [], "events": room_recent(lines)}
            season = season_series(path)
        else:
            pnl = trade_pnl()
            for line in lines:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                nr = r["neural"]
                events.append(
                    {
                        "tick": r["tick"],
                        "time": r["wall_time"],
                        "product": r["product"],
                        "bid": r["quote"]["bid"],
                        "equity": float(r["equity_usdc"]),
                        "pnl": float(r["pnl_delta_usdc"]),
                        "side": nr["side"],
                        "left_hz": nr["left_hz"],
                        "right_hz": nr["right_hz"],
                        "diff_hz": nr["difference_hz"],
                        "gate": nr["gate_spikes"],
                        "stimulus": nr["stimulus"],
                        "reward_spikes": nr["reward_spikes"],
                        "aversive_spikes": nr["aversive_spikes"],
                        "kc_spikes": nr["KC_spikes"],
                        "total_spikes": nr["total_spikes"],
                        "compute": nr["compute_seconds"],
                        "changed_edges": nr["memory"]["changed_edges"],
                        "mean_efficacy": nr["memory"]["mean_efficacy"],
                        "min_efficacy": nr["memory"]["minimum_efficacy"],
                        "execution": r["execution"].get("status"),
                        "reason": r["execution"].get("reason"),
                        "action": None, "fills": [], "liquidation": None, "funding": None,
                        "position": None, "room_events": [],
                        "trade_pnl": pnl.get(f"{r['execution'].get('base')}|{r['execution'].get('quote')}"),
                    }
                )
    cp = checkpoint()
    return {
        "run": RUN.name,
        "venue": "orangex-perp" if perp else "coinbase-spot",
        "fly_name": fly_name(RUN) if perp else "초파리",
        "settings": perp_settings(RUN) if perp else {},
        "now": time.time(),
        "events": events,
        "veto_ticks": vetoes,
        "orders_today": fills_today(RUN, time.time(), TZ_OFFSET) if perp else 0,
        "ledger": lg,
        "room": room,
        "season": season,
        "disclosure": DISCLOSURE,
        "stopped": (RUN / "STOP").exists(),
        "checkpoint": None
        if cp is None
        else {k: cp[k] for k in ["luminance", "r8_light", "efficacy_hist", "efficacy_edges", "brain_ms", "mtime"]},
    }


# ---- cached snapshot ------------------------------------------------------------------------------
# Every open viewer polls. Building the state reads 400 event lines and the ledger, so it is rebuilt
# only when a run file changed (looked at no more than once a second) and the bytes are shared.
# /live.json is versioned by the hash of its body: a viewer asks /tick.json for the version and
# fetches live.json?v=<version> only when it changed, which a CDN in front can cache forever.
_SNAP = {"key": None, "checked": -1.0}
_SNAP_LOCK = threading.Lock()
IMMUTABLE = "public, max-age=31536000, immutable"


def _stat(path):
    try:
        s = path.stat()
        return s.st_size, s.st_mtime_ns
    except OSError:
        return None


def run_version():
    cps = []
    for p in RUN.glob("brain-*.npz"):
        st = _stat(p)
        if st:
            cps.append((p.name, st[1]))
    return (
        _stat(RUN / "events.jsonl"), _stat(RUN / "ledger.sqlite"), _stat(RUN / "ledger.sqlite-wal"),
        _stat(RUN / "latest-input.png"), (RUN / "STOP").exists(), tuple(sorted(cps)),
        int((time.time() + TZ_OFFSET) // 86400),  # "today's trades" resets at local midnight
    )


def snapshot():
    with _SNAP_LOCK:
        mono = time.monotonic()
        if _SNAP["key"] is not None and mono - _SNAP["checked"] < 1.0:
            return dict(_SNAP)
        _SNAP["checked"] = mono
        key = run_version()
        if key == _SNAP["key"]:
            return dict(_SNAP)
        st = state()
        st.pop("now", None)
        live_body = json.dumps(live_payload(st), ensure_ascii=False, separators=(",", ":")).encode()
        cp = checkpoint()
        counts = cp["counts"] if cp else b""
        png = RUN / "latest-input.png"
        _SNAP.update(
            key=key, v=hashlib.sha1(live_body).hexdigest()[:12], tick=current_tick(st),
            halted=(st.get("ledger") or {}).get("halted"), stopped=bool(st.get("stopped")),
            state_body=json.dumps(st).encode(), live_body=live_body, live_gz=gzip.compress(live_body, 6),
            counts=counts, counts_gz=gzip.compress(counts, 6) if counts else b"",
            png=png.read_bytes() if png.exists() else None,
        )
        return dict(_SNAP)


class Handler(BaseHTTPRequestHandler):
    def accepts_gzip(self):
        return "gzip" in (self.headers.get("Accept-Encoding") or "").lower()

    def send(self, body, ctype, cache=False, gz=None):
        """200 with CORS (every route is public, read-only data). `cache` is True (one hour),
        False (no-store) or a Cache-Control string; `gz` is the pre-compressed body."""
        use_gz = gz is not None and self.accepts_gzip() and len(gz) < len(body)
        payload = gz if use_gz else body
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        if use_gz:
            self.send_header("Content-Encoding", "gzip")
        if gz is not None:
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", cache if isinstance(cache, str) else ("max-age=3600" if cache else "no-store"))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def versioned(self, snap):
        """Immutable caching only for a request that names the current version."""
        v = parse_qs(urlsplit(self.path).query).get("v", [None])[0]
        return IMMUTABLE if v and v == snap["v"] else "no-store"

    def send_range(self, path, ctype):
        # <video> needs byte ranges to seek and loop reliably.
        size = path.stat().st_size
        start, end = 0, size - 1
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with path.open("rb") as f:
                f.seek(start)
                self.wfile.write(f.read(end - start + 1))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        route = self.path.split("?")[0]
        if route in ("/", "/index.html"):
            return self.send((HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if route == "/flies.json":
            return self.send(json.dumps(FLIES).encode(), "application/json")
        if route in STATIC_BODIES:
            body, ctype = STATIC_BODIES[route]
            return self.send(body, ctype, True, gz_static(route))
        if route == "/tick.json":
            s = snapshot()
            body = json.dumps({"v": s["v"], "tick": s["tick"], "now": round(time.time(), 3),
                               "halted": s["halted"], "stopped": s["stopped"]}).encode()
            return self.send(body, "application/json")
        if route == "/live.json":
            s = snapshot()
            return self.send(s["live_body"], "application/json; charset=utf-8", self.versioned(s), s["live_gz"])
        if route == "/state.json":
            s = snapshot()
            body = b'{"now": %.3f, ' % time.time() + s["state_body"][1:]
            return self.send(body, "application/json", False, gzip.compress(body, 5) if self.accepts_gzip() else None)
        if route == "/counts.bin":
            s = snapshot()
            return self.send(s["counts"], "application/octet-stream", self.versioned(s), s["counts_gz"] or None)
        if route == "/input.png":
            s = snapshot()
            if s["png"] is not None:
                return self.send(s["png"], "image/png", self.versioned(s))
        if route == "/room/milestones.json" and MILESTONES.is_file():
            return self.send(MILESTONES.read_bytes(), "application/json", True)
        if route == "/room":
            # The studio loads its files relative to /room/ so the same page also works from a
            # sub-folder (GitHub Pages); keep the query (?demo=1, ?stream=1) across the redirect.
            q = urlsplit(self.path).query
            self.send_response(301)
            self.send_header("Location", "/room/" + (f"?{q}" if q else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if route == "/room/":
            return self.send((ROOM_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        r = re.fullmatch(r"/room/((?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(?:js|css|txt))", route)
        if r and ".." not in r.group(1):
            p = (ROOM_DIR / r.group(1)).resolve()
            if p.is_file() and ROOM_DIR.resolve() in p.parents:
                # Vendored three.js is immutable; the studio's own files must reload on every visit.
                return self.send(p.read_bytes(), ROOM_TYPES[p.suffix], r.group(1).startswith("vendor/"))
        f = re.fullmatch(r"/assets/fonts/([A-Za-z0-9_.-]+\.woff2)", route)
        if f and (FONT_DIR / f.group(1)).is_file():
            return self.send((FONT_DIR / f.group(1)).read_bytes(), "font/woff2", True)
        m = re.fullmatch(r"/anim/(buy|sell_profit|sell_loss|hold)\.mp4", route)
        if m and (ANIM_DIR / f"{m.group(1)}.mp4").is_file():
            return self.send_range(ANIM_DIR / f"{m.group(1)}.mp4", "video/mp4")
        self.send_error(404)

    do_HEAD = do_GET

    def do_OPTIONS(self):
        # CORS preflight for the web viewer on another origin (GitHub Pages); reads only.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # Read-only dashboard: refuse every method that could change state.
    def refuse(self):
        self.send_error(405, "Read-only dashboard")

    do_POST = do_PUT = do_PATCH = do_DELETE = refuse

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not (RUN / "events.jsonl").exists():
        print(f"Note: {RUN} has no events yet; start `python -m stonkfly run` first.", flush=True)
    print(f"Stonkfly dashboard: http://{HOST}:{PORT}  (run: {RUN.name})", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

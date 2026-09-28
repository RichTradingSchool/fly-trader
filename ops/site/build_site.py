"""Build the static web viewer (for GitHub Pages or any static host).

    python ops/site/build_site.py [--out site] [--run runs/s1] [--feed URL]
                                  [--repo-url URL] [--guide PATH] [--ref-url URL] [--community-url URL]
                                  [--files-url URL] [--apply-url URL]

Defaults for the repository, the site address, the community link, the download (files) link and the
challenge sign-up link come from ops/site/site.json; command-line flags override them (an empty value
turns a link off). The program is handed out through the files link (a Telegram archive), not the site.

The site mirrors the dashboard's URL layout, so the 3D studio page is byte-for-byte the
dashboard's except for one injected line that tells it to read feed.json:

    site/index.html                 landing page (ops/site/landing.html)
    site/feed.json                  {"feed": "<public dashboard address or empty>"}
    site/meta.json, pos.bin, …      the brain point cloud (from dashboard/cache)
    site/assets/fonts/…             Pretendard subset + licence
    site/room/…                     the studio (three.js vendored, no external requests)

With an empty feed (or an unreachable one) the studio plays the demo season.
Run it from the repository root after the dashboard has built dashboard/cache once.
"""

import argparse
import html
import json
import shutil
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboard"
HERE = Path(__file__).resolve().parent


def https_or_empty(url, what):
    url = (url or "").strip()
    if url and not url.startswith("https://"):
        raise SystemExit(f"{what} must be an https:// address: {url}")
    return url


def main():
    cfg = json.loads((HERE / "site.json").read_text(encoding="utf-8")) if (HERE / "site.json").is_file() else {}
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="site")
    p.add_argument("--run", default="runs/s1", help="run whose latest eye frame becomes the demo's sample")
    p.add_argument("--feed", default="", help="public dashboard address for feed.json (can be set later)")
    p.add_argument("--repo-url", default=cfg.get("repo_url", "https://github.com/RichTradingSchool/fly-trader"))
    p.add_argument("--site-url", default=cfg.get("site_url", "https://richtradingschool.github.io/fly-trader/"),
                   help="absolute address of the published site (link previews need an absolute og:image)")
    p.add_argument("--guide", default="", help="PDF copied to site/guide.pdf and linked from the landing page")
    p.add_argument("--ref-url", default="", help="optional exchange sign-up link shown on the landing page")
    p.add_argument("--community-url", default=cfg.get("community_url", ""),
                   help="community (e.g. Telegram) link on the landing page and the studio header")
    p.add_argument("--community-title", default=cfg.get("community_title", "커뮤니티"))
    p.add_argument("--files-url", default=cfg.get("files_url", ""),
                   help="where visitors download the program, guide and OBS scene (default: the community link, "
                        "then the repository)")
    p.add_argument("--apply-url", default=cfg.get("apply_url", ""),
                   help="challenge sign-up link shown under the live board and in the header (empty hides it)")
    p.add_argument("--apply-title", default=cfg.get("apply_title", "챌린지 참가 신청"))
    p.add_argument("--apply-text", default=cfg.get("apply_text", "초파리와 함께하는 트레이딩 챌린지에 참가하고 싶다면 지금 신청하세요."))
    p.add_argument("--apply-button", default=cfg.get("apply_button", "챌린지 신청하기"))
    a = p.parse_args()
    community = https_or_empty(a.community_url, "--community-url")
    apply = https_or_empty(a.apply_url, "--apply-url")
    files = https_or_empty(a.files_url, "--files-url") or community or a.repo_url

    out = Path(a.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    (out / "room").mkdir(parents=True)

    cache = DASH / "cache"
    if not (cache / "static.npz").exists() or not (cache / "hop.npy").exists():
        raise SystemExit("dashboard/cache is missing: start the dashboard once (python dashboard/server.py …) to build it")
    z = np.load(cache / "static.npz")
    (out / "pos.bin").write_bytes(z["pos"].astype(np.float32).tobytes())
    (out / "sc.bin").write_bytes(z["sc"].astype(np.uint8).tobytes())
    (out / "type.bin").write_bytes(z["type"].astype(np.uint16).tobytes())
    (out / "hop.bin").write_bytes(np.load(cache / "hop.npy").astype(np.uint8).tobytes())
    shutil.copyfile(cache / "meta.json", out / "meta.json")

    shutil.copytree(DASH / "assets" / "fonts", out / "assets" / "fonts", ignore=shutil.ignore_patterns(".gitkeep"))

    room = DASH / "room"
    for f in room.iterdir():
        if f.is_dir():
            shutil.copytree(f, out / "room" / f.name)
        elif f.suffix in (".js", ".txt"):
            shutil.copyfile(f, out / "room" / f.name)
    page = (room / "index.html").read_text(encoding="utf-8")
    marker = "<!--SITE-CONFIG-->"
    if marker not in page:
        raise SystemExit("room/index.html has no <!--SITE-CONFIG--> marker")
    site_cfg = {"feedIndex": "../feed.json"}
    if community:
        site_cfg["community"] = community
    site_cfg = json.dumps(site_cfg).replace("<", "\\u003c")  # safe inside <script>
    (out / "room" / "index.html").write_text(page.replace(marker, f"<script>window.FLY_SITE={site_cfg}</script>"),
                                             encoding="utf-8")
    milestones = ROOT / "stonkfly" / "perp" / "milestones.json"
    if milestones.is_file():
        shutil.copyfile(milestones, out / "room" / "milestones.json")
    eye = Path(a.run) / "latest-input.png"
    if eye.is_file():
        shutil.copyfile(eye, out / "room" / "sample-eye.png")

    feed = {"feed": a.feed.rstrip("/"), "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out / "feed.json").write_text(json.dumps(feed, ensure_ascii=False) + "\n", encoding="utf-8")

    guide = ""
    if a.guide:
        shutil.copyfile(a.guide, out / "guide.pdf")
        guide = "guide.pdf"
    landing = (HERE / "landing.html").read_text(encoding="utf-8")
    icon = lambda name: f'<svg class="i"><use href="#i-{name}"/></svg>'  # symbols live in landing.html
    ref_block = ""
    if a.ref_url:
        u = html.escape(a.ref_url, quote=True)
        ref_block = (f'<section class="ref-sec"><div class="wrap"><div class="ref"><div><span class="eyebrow">EXCHANGE</span>'
                     f'<h2>실전은 선물거래소에서</h2><p class="sub">이 프로그램은 BTC 무기한 선물(OrangeX 공개 시세)을 기준으로 '
                     f'만들었습니다. 아래 링크로 가입하면 전용 이벤트와 혜택이 적용됩니다.</p></div>'
                     f'<a class="btn ghost lg" href="{u}" target="_blank" rel="noopener">OrangeX 가입하기{icon("arrow")}</a>'
                     f'</div></div></section>')
    nav = btn = section = ""
    if community:
        c, title = html.escape(community, quote=True), html.escape(a.community_title)
        nav = f'<a href="{c}" target="_blank" rel="noopener">커뮤니티</a>'
        btn = f'<a class="textlink" href="{c}" target="_blank" rel="noopener">{icon("send")}텔레그램 커뮤니티 입장{icon("arrow")}</a>'
        section = (
            f'<section id="community" class="tg-sec"><div class="wrap"><div class="tgc">'
            f'<div class="tg-text"><span class="eyebrow">TELEGRAM COMMUNITY</span>'
            f'<h2>{title}</h2>'
            f'<p class="sub">시장을 움직이는 경제뉴스를 실시간으로 받아 보고, 초파리 챌린지 제작 파일과 업데이트 소식을 한곳에서 챙길 수 있는 '
            f'텔레그램 커뮤니티입니다.</p>'
            f'<ul class="tg-list"><li>{icon("news")}실시간 경제뉴스 · 지표 발표 알림</li>'
            f'<li>{icon("folder")}제작 파일 자료실 · 가이드 · 방송 장면</li>'
            f'<li>{icon("fly")}초파리 시즌 소식 · 하이라이트</li></ul></div>'
            f'<a class="btn tg xl" href="{c}" target="_blank" rel="noopener">{icon("send")}텔레그램 입장하기</a></div></div></section>')
    top_cta = f'<a class="btn sm gold top-cta" href="room/">{icon("play")}3D 라이브</a>'
    apply_block = ""
    if apply:
        u = html.escape(apply, quote=True)
        top_cta = f'<a class="btn sm gold top-cta" href="{u}" target="_blank" rel="noopener">챌린지 신청{icon("arrow")}</a>'
        apply_block = (
            f'<div class="apply" id="apply"><div class="apply-text"><span class="eyebrow">JOIN THE CHALLENGE</span>'
            f'<h3>{html.escape(a.apply_title)}</h3><p>{html.escape(a.apply_text)}</p></div>'
            f'<a class="btn gold xl" href="{u}" target="_blank" rel="noopener">{html.escape(a.apply_button)}{icon("arrow")}</a></div>')
    for key, value in {
        "{{SITE_URL}}": html.escape(a.site_url.rstrip("/") + "/", quote=True),
        "{{REPO_URL}}": html.escape(a.repo_url, quote=True),
        "{{FILES_URL}}": html.escape(files, quote=True),
        "{{GUIDE_URL}}": guide,
        "{{BUILT}}": time.strftime("%Y-%m-%d"),
        "<!--REF-->": ref_block,
        "<!--COMMUNITY-NAV-->": nav,
        "<!--COMMUNITY-BTN-->": btn,
        "<!--COMMUNITY-->": section,
        "<!--TOP-CTA-->": top_cta,
        "<!--APPLY-->": apply_block,
    }.items():
        landing = landing.replace(key, value)
    (out / "index.html").write_text(landing, encoding="utf-8")
    og = HERE / "og.png"
    if og.is_file():
        shutil.copyfile(og, out / "og.png")
    (out / ".nojekyll").write_text("")

    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"built {out} ({size / 1e6:.1f} MB), feed={feed['feed'] or '(none: demo)'}")


if __name__ == "__main__":
    main()

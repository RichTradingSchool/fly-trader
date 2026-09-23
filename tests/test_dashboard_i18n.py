import re
from pathlib import Path

HTML = Path("dashboard/index.html")
HAN = re.compile(r"[一-鿿㐀-䶿]")


def test_no_chinese_characters_remain():
    text = HTML.read_text(encoding="utf-8")
    bad = [i + 1 for i, line in enumerate(text.splitlines()) if HAN.search(line)]
    assert bad == [], f"CJK ideographs remain on lines {bad}"


def test_lang_font_and_no_external_resources():
    text = HTML.read_text(encoding="utf-8")
    assert '<html lang="ko">' in text
    assert '@font-face{font-family:"Pretendard Variable"' in text
    assert "fonts.googleapis.com" not in text and "cdn." not in text and "http://" not in text.split("<script>")[0]


def test_canvas_guard_present():
    text = HTML.read_text(encoding="utf-8")
    assert "< 2) return;" in text and "Math.max(320," in text and "if (!img) return;" in text


def test_position_card_and_disclosure_wired():
    text = HTML.read_text(encoding="utf-8")
    for token in ['id="posCard"', 'id="posLiq"', 'id="posUpnl"', 'id="posRealized"', 'id="disclosure"',
                  'id="tradesToday"', 'id="nextFunding"', 'id="seasonCard"', 'function sideLabel(e)',
                  "e.liquidation ? {i", "shape === 'x'", "shape === 'diamond'", "STATE.disclosure", "STATE.fly_name",
                  "STATE.orders_today", "STATE.season", "STATE.settings", "lg.started_at",
                  'grid-template-areas:"eye dec" "pos da" "season fly"', "repeat(6,minmax(0,1fr))", "시세 실패"]:
        assert token in text, token
    # the disclosure strip must render before drawPanels' early return so it shows even with zero events
    assert text.index("$('#disclosure').innerHTML") < text.index("if (!e) return;")
    assert 'id="posNext"' not in text  # the funding countdown moved to the top strip


def test_disclosure_strip_is_inside_the_16_9_stage():
    # Below the footer it is off camera in every recording (spec §7.2: always displayed).
    text = HTML.read_text(encoding="utf-8")
    assert text.index('<p class="foot" id="disclosure"></p>') < text.index("<!-- /stage -->")
    assert "body.staged #disclosure{" in text


def test_only_glyphs_the_subset_font_has():
    # Pretendard's subset has no U+2715 ✕, U+27F2 ⟲; × and ↺ render, ❚❚ falls back on purpose.
    text = HTML.read_text(encoding="utf-8")
    for bad in ["✕", "⟲"]:
        assert bad not in text, bad


def test_replacements_are_idempotent(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("i18n_ko", Path("tools/i18n_ko.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    copy = tmp_path / "index.html"
    copy.write_text(HTML.read_text(encoding="utf-8"), encoding="utf-8")
    assert m.apply(copy) == 0  # already applied to the committed file

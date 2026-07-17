# Requires one-time browser install before running locally:
#   python -m playwright install chromium
#
# Covers the iOS/iPad touch pass (Phase 3): no-horizontal-scroll at phone
# width, the laser "Move to pad" touch fallback for drag/drop reassignment,
# and the LED Pad page loading cleanly at phone width. These are
# SOFTWARE-VALIDATED ONLY checks (rendered layout + API round trips run in a
# headless browser); they do not prove on-device iOS Safari behavior.
from __future__ import annotations

import re
import unittest

try:
    from playwright.sync_api import Page, expect
except ImportError as exc:
    raise unittest.SkipTest(f"playwright not installed: {exc}") from exc

IPHONE_VIEWPORT = {"width": 390, "height": 844}


def _no_horizontal_scroll(page: Page) -> bool:
    return page.evaluate(
        "() => document.documentElement.scrollWidth <= window.innerWidth"
    )


def test_laser_pad_no_horizontal_scroll_at_iphone_width(page: Page, laser_pad_server) -> None:
    page.set_viewport_size(IPHONE_VIEWPORT)
    page.goto(laser_pad_server.base_url)
    expect(page.locator(".title-chip")).to_contain_text("LASER PAD")
    expect(page.locator(".note-grid .note-btn").first).to_be_visible()

    assert _no_horizontal_scroll(page)


def test_laser_pad_move_to_pad_reassigns_mapping(page: Page, laser_pad_server) -> None:
    page.goto(laser_pad_server.base_url)
    expect(page.locator(".note-grid .note-btn").first).to_be_visible()

    page.get_by_role("button", name=re.compile(r"Bank 2")).click()
    expect(page.locator(".bank-tab.active")).to_contain_text("Bank 2")

    # Long-press (right-click fires the same @contextmenu.prevent handler
    # used as the desktop long-press affordance) mapped pad 37 to open the
    # mapping drawer.
    page.locator(".note-btn", has_text="37").first.click(button="right")
    expect(page.locator(".mapping-drawer")).to_be_visible()

    move_select = page.locator(".mapping-drawer").get_by_label("Move to pad:")
    expect(move_select).to_be_visible()

    with page.expect_response("**/api/draft"):
        move_select.select_option("32")

    payload = page.evaluate("() => fetch('/api/config').then((r) => r.json())")
    assert payload["config"]["scenes"]["house_groove_1"]["midi"]["note"] == 32
    # The select resets to its placeholder after a successful move.
    expect(move_select).to_have_value("")


def test_led_pad_loads_at_iphone_width_without_console_errors(page: Page, led_pad_server) -> None:
    console_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    page.set_viewport_size(IPHONE_VIEWPORT)
    page.goto(led_pad_server.base_url)
    expect(page.locator(".look-grid")).to_be_visible()

    assert console_errors == []
    assert _no_horizontal_scroll(page)


# --------------------------------------------------------------------------- #
# AWR-280 — phone-first pad shell: first tile high, STOP reachable, fold folds.
# --------------------------------------------------------------------------- #
def test_led_pad_first_tile_in_top_quarter_at_phone_width(page: Page, led_pad_server) -> None:
    """The compact header must put the first look tile in the top 25% of the phone."""
    page.set_viewport_size(IPHONE_VIEWPORT)
    page.goto(led_pad_server.base_url)
    expect(page.locator("#lookGrid .look-card").first).to_be_visible()
    frac = page.evaluate(
        "() => { const t = document.querySelector('#lookGrid .look-card');"
        " const r = t.getBoundingClientRect(); return r.top / window.innerHeight; }"
    )
    assert frac <= 0.25, f"first tile at {frac:.3f} of viewport (want <= 0.25)"
    assert _no_horizontal_scroll(page)


def test_led_pad_stop_hit_testable_with_editor_drawer_open_at_phone_width(
    page: Page, led_pad_server
) -> None:
    """AWR-279 STOP reachability, verified at phone width with the drawer open."""
    page.set_viewport_size(IPHONE_VIEWPORT)
    page.goto(led_pad_server.base_url)
    expect(page.locator("#lookGrid .look-card").first).to_be_visible()
    page.locator('#lookGrid .look-card [data-action="edit"]').first.click()
    expect(page.locator("#editorDrawer")).to_be_visible()

    hit = page.evaluate(
        "() => { const s = document.getElementById('stopBtn');"
        " const r = s.getBoundingClientRect();"
        " const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);"
        " return { h: r.height, hit: s.contains(el) || el === s }; }"
    )
    assert hit["hit"], f"STOP occluded with drawer open: {hit}"
    assert hit["h"] >= 44, f"STOP under 44px: {hit}"


def test_led_pad_session_fold_collapsed_by_default_at_phone_width(
    page: Page, led_pad_server
) -> None:
    """The session controls collapse into one tap-to-open row on the phone."""
    page.set_viewport_size(IPHONE_VIEWPORT)
    page.goto(led_pad_server.base_url)
    expect(page.locator("#lookGrid .look-card").first).to_be_visible()

    fold = page.locator("#sessionFold")
    assert page.evaluate("() => document.getElementById('sessionFold').open") is False
    page.locator(".session-fold-summary").click()
    assert page.evaluate("() => document.getElementById('sessionFold').open") is True
    expect(page.locator("#bpmInput")).to_be_visible()


def test_led_pad_desktop_session_fold_is_open_inline(page: Page, led_pad_server) -> None:
    """Above 700px the fold renders inline (open) — the desktop header is unchanged."""
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(led_pad_server.base_url)
    expect(page.locator(".look-grid")).to_be_visible()
    assert page.evaluate("() => document.getElementById('sessionFold').open") is True
    expect(page.locator("#bpmInput")).to_be_visible()
    # The summary is display:none on desktop.
    summary_display = page.evaluate(
        "() => getComputedStyle(document.querySelector('.session-fold-summary')).display"
    )
    assert summary_display == "none", summary_display

# Requires one-time browser install before running locally:
#   python -m playwright install chromium
#
# Covers the editor drawer's "unset param shows renderer default" fix
# (AWR-113 follow-up): 65 of 72 example-config looks store no params at all,
# and the pre-fix drawer rendered those unset controls at the widget's
# minimum instead of the renderer's actual fallback. SOFTWARE-VALIDATED
# ONLY: this proves the rendered DOM/state round trip in a headless browser,
# not hardware LED behavior.
from __future__ import annotations

import unittest

try:
    from playwright.sync_api import Page, expect
except ImportError as exc:
    raise unittest.SkipTest(f"playwright not installed: {exc}") from exc

# rt_buildup_ramp_3 (scene_ref="buildup_ramp_3") ships with params={} in the
# example config. Its "duration_beats" control has min=0 but the renderer's
# actual fallback (govee_frame_renderer.py:363, _EDM_DURATION_BEATS) is 32 -
# a case where the old min-fallback display (0) and the real default (32)
# visibly disagree, so it is a good canary for the fix.
_LOOK_NAME = "rt_buildup_ramp_3"


def _open_editor(page: Page, led_pad_server) -> None:
    page.goto(led_pad_server.base_url)
    expect(page.locator(".look-grid")).to_be_visible()

    payload = page.evaluate("() => fetch('/api/config').then((r) => r.json())")
    bank = next(
        bank for bank, names in payload["banks"].items() if _LOOK_NAME in names
    )
    page.locator(f'[data-bank="{bank}"]').click()

    edit_btn = page.locator(f'[data-action="edit"][data-name="{_LOOK_NAME}"]')
    expect(edit_btn).to_be_visible()
    edit_btn.click()
    expect(page.locator("#editorDrawer")).to_be_visible()


def test_unset_param_shows_renderer_default_not_control_minimum(
    page: Page, led_pad_server
) -> None:
    _open_editor(page, led_pad_server)

    duration_output = page.locator('[data-output="duration_beats"]')
    expect(duration_output).to_be_visible()
    expect(duration_output).to_contain_text("32")
    expect(duration_output.locator(".default-tag")).to_be_visible()
    # The pre-fix bug rendered unset params at the control's minimum (0) as
    # if it were the real value.
    assert duration_output.inner_text().strip().split("\n")[0] != "0"

    duration_input = page.locator('input[data-param="duration_beats"]')
    expect(duration_input).to_have_value("32")

    reset_btn = page.locator('[data-reset="duration_beats"]')
    expect(reset_btn).to_be_hidden()


def test_editing_control_clears_default_tag_and_reveals_reset(
    page: Page, led_pad_server
) -> None:
    _open_editor(page, led_pad_server)

    duration_output = page.locator('[data-output="duration_beats"]')
    duration_input = page.locator('input[data-param="duration_beats"]')
    reset_btn = page.locator('[data-reset="duration_beats"]')

    duration_input.fill("40")
    duration_input.dispatch_event("input")

    expect(duration_output).to_contain_text("40")
    expect(duration_output.locator(".default-tag")).to_have_count(0)
    expect(reset_btn).to_be_visible()

    reset_btn.click()

    expect(duration_output).to_contain_text("32")
    expect(duration_output.locator(".default-tag")).to_be_visible()
    expect(reset_btn).to_be_hidden()
    expect(duration_input).to_have_value("32")


def test_close_after_save_skips_discard_modal(page: Page, led_pad_server) -> None:
    """AWR-254: dirty close compares against last save, not editor-open snapshot."""
    _open_editor(page, led_pad_server)

    duration_input = page.locator('input[data-param="duration_beats"]')
    duration_input.fill("40")
    duration_input.dispatch_event("input")
    expect(page.locator("#dirtyText")).to_contain_text("Unsaved changes")
    expect(page.locator("#saveLookBtn")).to_be_enabled()

    page.locator("#saveLookBtn").click()
    expect(page.locator("#dirtyText")).to_contain_text("Draft saved")
    expect(page.locator("#saveLookBtn")).to_be_disabled()

    page.locator("#closeEditorBtn").click()
    expect(page.locator("#modal")).to_be_hidden()
    expect(page.locator("#editorDrawer")).to_be_hidden()


def test_close_with_unsaved_edits_shows_discard_modal(page: Page, led_pad_server) -> None:
    """AWR-254: closing with edits since last save still asks before discarding."""
    _open_editor(page, led_pad_server)

    duration_input = page.locator('input[data-param="duration_beats"]')
    duration_input.fill("44")
    duration_input.dispatch_event("input")

    page.locator("#closeEditorBtn").click()
    expect(page.locator("#modal")).to_be_visible()
    expect(page.locator("#modalTitle")).to_have_text("Discard unsaved changes?")
    expect(page.locator("#modalText")).to_contain_text("edits since your last save")

    page.locator('#modalActions button:has-text("Discard")').click()
    expect(page.locator("#modal")).to_be_hidden()
    expect(page.locator("#editorDrawer")).to_be_hidden()


def _open_named_look(page: Page, led_pad_server, look_name: str) -> None:
    page.goto(led_pad_server.base_url)
    expect(page.locator(".look-grid")).to_be_visible()
    payload = page.evaluate("() => fetch('/api/config').then((r) => r.json())")
    bank = next(bank for bank, names in payload["banks"].items() if look_name in names)
    page.locator(f'[data-bank="{bank}"]').click()
    page.locator(f'[data-action="edit"][data-name="{look_name}"]').click()
    expect(page.locator("#editorDrawer")).to_be_visible()


def test_awr262_solid_and_drop_strobe_hide_motion_params(page: Page, led_pad_server) -> None:
    """AWR-262: continuous/strobe looks show zero comet-motion knobs."""
    _open_named_look(page, led_pad_server, "rt_drop_strobe_blue")
    for key in ("travel_beats", "width", "trail_beats", "max_pulses", "heads", "sync_mode"):
        expect(page.locator(f'[data-param="{key}"]')).to_have_count(0)
    expect(page.locator("#advancedDetails")).to_be_hidden()

    # Switch renderer to solid — still no motion knobs; honesty modal if params drop.
    page.locator("#rendererSelect").select_option("solid")
    modal = page.locator("#modal")
    if modal.is_visible():
        page.locator('#modalActions button:has-text("Switch")').click()
    expect(page.locator('[data-param="travel_beats"]')).to_have_count(0)
    expect(page.locator('[data-param="heads"]')).to_have_count(0)
    expect(page.locator("#advancedDetails")).to_be_hidden()


def test_awr262_comet_motion_look_shows_motion_params(page: Page, led_pad_server) -> None:
    """AWR-262: comet-motion look shows motion knobs; never Comet Count/heads."""
    # Example bank lists rt_groove_chase (Class C); switch to a Class A comet.
    _open_named_look(page, led_pad_server, "rt_groove_chase")
    page.locator("#rendererSelect").select_option("groove_chase_blue")
    modal = page.locator("#modal")
    if modal.is_visible():
        page.locator('#modalActions button:has-text("Switch")').click()
    expect(page.locator("#advancedDetails")).to_be_visible()
    page.locator("#advancedDetails summary").click()
    expect(page.locator('[data-param="travel_beats"]')).to_be_visible()
    expect(page.locator('[data-param="width"]')).to_be_visible()
    expect(page.locator('[data-param="heads"]')).to_have_count(0)
    expect(page.get_by_text("Comet Count")).to_have_count(0)


def test_awr262_color_mode_is_word_dropdown(page: Page, led_pad_server) -> None:
    """AWR-262 C4: Color Mode is a select with word labels, not bare integers."""
    _open_named_look(page, led_pad_server, "rt_groove_heartbeat")
    expect(page.locator("#advancedDetails")).to_be_visible()
    page.locator("#advancedDetails summary").click()
    select = page.locator('select[data-param="color_mode"]')
    expect(select).to_be_visible()
    labels = select.locator("option").all_text_contents()
    assert any("slot" in label.lower() for label in labels)
    assert not any(label.strip().isdigit() for label in labels)


if __name__ == "__main__":
    unittest.main()

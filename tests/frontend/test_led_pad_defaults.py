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


if __name__ == "__main__":
    unittest.main()

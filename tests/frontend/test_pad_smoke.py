from __future__ import annotations

import re
import unittest

try:
    from playwright.sync_api import Page, expect
except ImportError as exc:
    raise unittest.SkipTest(f"playwright not installed: {exc}") from exc


def _goto(page: Page, laser_pad_server) -> list[str]:
    console_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    page.goto(laser_pad_server.base_url)
    expect(page.locator(".title-chip")).to_contain_text("LASER PAD")
    expect(page.locator(".note-grid .note-btn").first).to_be_visible()
    return console_errors


def _open_bank_2(page: Page) -> None:
    page.get_by_role("button", name=re.compile(r"Bank 2")).click()
    expect(page.locator(".bank-tab.active")).to_contain_text("Bank 2")


def _select_editor_personality(page: Page, name: str) -> None:
    with page.expect_response("**/api/draft"):
        page.locator(".pad-editor-toolbar select").select_option(name)
    expect(page.locator(".pad-editor-toolbar select")).to_have_value(name)


def test_page_loads_without_console_errors(page: Page, laser_pad_server) -> None:
    console_errors = _goto(page, laser_pad_server)

    assert console_errors == []


def test_personality_dropdown_updates_editor_heading(page: Page, laser_pad_server) -> None:
    _goto(page, laser_pad_server)

    page.get_by_role("button", name="Settings").click()
    page.get_by_role("button", name="Personalities").click()
    _select_editor_personality(page, "dubstep")

    expect(page.locator(".settings-personality-editor h4")).to_have_text("dubstep")


def test_click_mapped_pad_calls_test_note(page: Page, laser_pad_server) -> None:
    _goto(page, laser_pad_server)
    _open_bank_2(page)

    with page.expect_request("**/api/test_note"):
        page.locator(".note-btn", has_text="37").first.click()


def test_cmd_click_mapped_pad_adds_scene_to_dubstep_role_bank(
    page: Page, laser_pad_server
) -> None:
    _goto(page, laser_pad_server)
    _select_editor_personality(page, "dubstep")
    _open_bank_2(page)

    with page.expect_response("**/api/draft"):
        page.locator(".note-btn", has_text="37").first.click(modifiers=["Meta"])
    payload = page.evaluate("() => fetch('/api/config').then((r) => r.json())")

    assert "house_groove_1" in payload["config"]["personalities"]["dubstep"]["phrase_bank"]


def test_shared_scene_refs_do_not_show_duplicate_warning(
    page: Page, laser_pad_server
) -> None:
    _goto(page, laser_pad_server)

    warning = page.evaluate(
        "() => window.Alpine.$data(document.body).computeDuplicateWarning()"
    )

    assert warning == ""


def test_distinct_scenes_on_same_midi_key_show_duplicate_warning(
    page: Page, laser_pad_server
) -> None:
    config = laser_pad_server.service.get_config_payload()["config"]
    template = config["scenes"]["house_groove_1"]

    response = laser_pad_server.service.apply_draft_patch({
        "patch": {
            "scenes": {"dup_test_scene": {**template, "label": "Dup Test"}},
            "personalities": {"dubstep": {"phrase_bank": ["dup_test_scene"]}},
        },
    })
    assert response.get("ok"), response

    _goto(page, laser_pad_server)

    warning = page.evaluate(
        "() => window.Alpine.$data(document.body).computeDuplicateWarning()"
    )

    assert warning, warning
    assert "1:37" in warning


def test_personality_color_persists_to_pad_meta(page: Page, laser_pad_server) -> None:
    _goto(page, laser_pad_server)
    page.get_by_role("button", name="Settings").click()
    page.get_by_role("button", name="Personalities").click()
    row = page.locator(".settings-personality-row").filter(has_text="dubstep")
    color = row.locator('input[type="color"]')

    with page.expect_response("**/api/draft"):
        color.evaluate(
            "(el) => { el.value = '#abcdef'; el.dispatchEvent(new Event('change', { bubbles: true })); }"
        )
    payload = page.evaluate("() => fetch('/api/config').then((r) => r.json())")

    assert (
        payload["config"]["_pad_meta"]["personality_colors"]["dubstep"]["color"]
        == "#abcdef"
    )


def test_save_apply_clean_draft_writes_backup(page: Page, laser_pad_server) -> None:
    _goto(page, laser_pad_server)
    before = set(laser_pad_server.config_dir.glob("laser_director.json.bak-*"))

    with page.expect_response("**/api/commit"):
        page.get_by_role("button", name=re.compile(r"Save & Apply")).click()
    expect(page.locator(".save-badge")).to_contain_text("Applied")
    after = set(laser_pad_server.config_dir.glob("laser_director.json.bak-*"))

    assert after - before

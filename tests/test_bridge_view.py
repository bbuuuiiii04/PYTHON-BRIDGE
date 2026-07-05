from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import bridge_view  # noqa: E402


class ParseRecordTest(unittest.TestCase):
    def test_valid_json_object_returns_dict(self) -> None:
        rec = bridge_view.parse_record(
            '{"ts": 1.0, "lvl": "INFO", "cat": "perf.deck", "msg": "hi", "src": "state_manager"}'
        )
        self.assertEqual(rec["cat"], "perf.deck")
        self.assertEqual(rec["msg"], "hi")

    def test_blank_line_returns_none(self) -> None:
        self.assertIsNone(bridge_view.parse_record(""))

    def test_whitespace_only_line_returns_none(self) -> None:
        self.assertIsNone(bridge_view.parse_record("   \n"))

    def test_truncated_json_returns_none(self) -> None:
        # A bridge-death partial write: the file-follower may hand this a
        # trailing fragment. Must never raise.
        self.assertIsNone(bridge_view.parse_record('{"ts": 1.0, "cat": "sys.b'))

    def test_garbage_text_returns_none(self) -> None:
        self.assertIsNone(bridge_view.parse_record("not json at all"))

    def test_json_array_is_not_a_record(self) -> None:
        self.assertIsNone(bridge_view.parse_record("[1, 2, 3]"))

    def test_json_scalar_is_not_a_record(self) -> None:
        self.assertIsNone(bridge_view.parse_record("42"))

    def test_unknown_extra_fields_pass_through(self) -> None:
        rec = bridge_view.parse_record('{"cat": "x", "totally_new_field": 7}')
        self.assertEqual(rec["totally_new_field"], 7)

    def test_trailing_newline_is_stripped(self) -> None:
        rec = bridge_view.parse_record('{"cat": "x"}\n')
        self.assertEqual(rec["cat"], "x")


class LensOfTest(unittest.TestCase):
    def test_perf_prefixed_cat_is_performance(self) -> None:
        rec = {"cat": "perf.laser.scene", "lvl": "INFO", "src": "laser_director"}
        self.assertIn("PERFORMANCE", bridge_view.lens_of(rec))

    def test_non_perf_cat_is_not_performance(self) -> None:
        rec = {"cat": "state_manager", "lvl": "WARNING", "src": "state_manager"}
        self.assertNotIn("PERFORMANCE", bridge_view.lens_of(rec))

    def test_warning_level_is_operator_regardless_of_cat(self) -> None:
        rec = {"cat": "state_manager", "lvl": "WARNING", "src": "state_manager"}
        self.assertIn("OPERATOR", bridge_view.lens_of(rec))

    def test_error_level_is_operator(self) -> None:
        rec = {"cat": "anything", "lvl": "ERROR", "src": "anything"}
        self.assertIn("OPERATOR", bridge_view.lens_of(rec))

    def test_info_level_non_health_is_not_operator(self) -> None:
        rec = {"cat": "state_manager", "lvl": "INFO", "src": "state_manager"}
        self.assertNotIn("OPERATOR", bridge_view.lens_of(rec))

    def test_health_prefixed_cat_is_operator_regardless_of_level(self) -> None:
        rec = {"cat": "health.midi", "lvl": "INFO", "src": "midi_output"}
        self.assertIn("OPERATOR", bridge_view.lens_of(rec))

    def test_sys_prefixed_cat_is_system(self) -> None:
        rec = {"cat": "sys.thread", "lvl": "INFO", "src": "bridge"}
        self.assertIn("SYSTEM", bridge_view.lens_of(rec))

    def test_health_prefixed_cat_is_also_system(self) -> None:
        rec = {"cat": "health.midi", "lvl": "WARNING", "src": "midi_output"}
        lenses = bridge_view.lens_of(rec)
        self.assertIn("SYSTEM", lenses)
        self.assertIn("OPERATOR", lenses)

    def test_legacy_infra_src_at_info_is_system(self) -> None:
        rec = {"cat": "rb_state", "lvl": "INFO", "src": "rb_memory"}
        self.assertIn("SYSTEM", bridge_view.lens_of(rec))

    def test_legacy_infra_src_at_warning_is_system(self) -> None:
        rec = {"cat": "rb_memory", "lvl": "WARNING", "src": "rb_memory"}
        self.assertIn("SYSTEM", bridge_view.lens_of(rec))

    def test_legacy_infra_src_at_debug_is_not_system(self) -> None:
        # The level gate: DEBUG-level chatter from a legacy-infra module must
        # not reach SYSTEM (see lens_of's deviation docstring).
        rec = {"cat": "rb_memory", "lvl": "DEBUG", "src": "rb_memory"}
        self.assertNotIn("SYSTEM", bridge_view.lens_of(rec))

    def test_non_legacy_src_at_info_is_not_system(self) -> None:
        rec = {"cat": "some_module", "lvl": "INFO", "src": "some_module"}
        self.assertNotIn("SYSTEM", bridge_view.lens_of(rec))

    def test_every_record_is_debug(self) -> None:
        for lvl in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            rec = {"cat": "anything", "lvl": lvl, "src": "anything"}
            self.assertIn("DEBUG", bridge_view.lens_of(rec))

    def test_rb_memory_candidate_debug_excluded_from_performance_and_operator(self) -> None:
        """Required test (spec Part B, Task W6): a DEBUG record with cat
        "rb_memory" (candidate-spam shape, e.g. rb_memory.py's
        [RBMEM][CANDIDATE]/[REJECT] lines, which are confirmed to stay DEBUG
        today) must route to the DEBUG lens ONLY.

        rb_memory's real logger name IS exactly "rb_memory" (confirmed
        logging.getLogger("rb_memory") at rb_memory.py:40), so both cat and
        src are "rb_memory" for a genuine candidate-spam record -- meaning a
        LEVEL-BLIND "src in LEGACY_INFRA" clause would also match SYSTEM.
        lens_of's level gate on that clause (see its docstring) is what makes
        this assertion -- and the general "pollutes MAX DEBUG only"
        guarantee, design doc Section 2.1 -- actually hold.
        """
        rec = {
            "ts": 1751685243.5, "mono": 100.0, "lvl": "DEBUG",
            "cat": "rb_memory", "src": "rb_memory",
            "msg": "[RBMEM][CANDIDATE] deck2 zone pos=0x1234 inner=0x1230 rate=1.2",
        }
        self.assertEqual(bridge_view.lens_of(rec), {"DEBUG"})

    def test_missing_cat_and_lvl_does_not_raise(self) -> None:
        self.assertEqual(bridge_view.lens_of({}), {"DEBUG"})

    def test_non_string_cat_and_lvl_does_not_raise(self) -> None:
        rec = {"cat": 123, "lvl": 30, "src": ["weird"]}
        self.assertEqual(bridge_view.lens_of(rec), {"DEBUG"})


class StrFieldAndLevelNoTest(unittest.TestCase):
    def test_str_field_missing_key(self) -> None:
        self.assertEqual(bridge_view._str_field({}, "cat"), "")

    def test_str_field_non_string_value(self) -> None:
        self.assertEqual(bridge_view._str_field({"cat": 5}, "cat"), "")

    def test_str_field_string_passthrough(self) -> None:
        self.assertEqual(bridge_view._str_field({"cat": "x"}, "cat"), "x")

    def test_level_no_missing(self) -> None:
        self.assertEqual(bridge_view._level_no({}), 0)

    def test_level_no_unknown_name(self) -> None:
        self.assertEqual(bridge_view._level_no({"lvl": "TRACE"}), 0)

    def test_level_no_non_string_value(self) -> None:
        self.assertEqual(bridge_view._level_no({"lvl": 30}), 0)

    def test_level_no_known_names(self) -> None:
        self.assertEqual(bridge_view._level_no({"lvl": "DEBUG"}), 10)
        self.assertEqual(bridge_view._level_no({"lvl": "INFO"}), 20)
        self.assertEqual(bridge_view._level_no({"lvl": "WARNING"}), 30)
        self.assertEqual(bridge_view._level_no({"lvl": "ERROR"}), 40)
        self.assertEqual(bridge_view._level_no({"lvl": "CRITICAL"}), 50)


class FriendlyMapTest(unittest.TestCase):
    def test_contains_the_literal_spec_example(self) -> None:
        self.assertEqual(bridge_view.FRIENDLY["perf.laser.scene"], "laser")

    def test_values_are_short_plain_words_no_brackets(self) -> None:
        for value in bridge_view.FRIENDLY.values():
            self.assertNotIn("[", value)
            self.assertNotIn("]", value)
            self.assertLess(len(value), 16)


class FormatLineTest(unittest.TestCase):
    def test_segments_concatenate_to_expected_fixed_column_line(self) -> None:
        ts = 1751685243.5
        rec = {
            "ts": ts, "lvl": "INFO", "cat": "perf.laser.scene", "src": "laser_director",
            "msg": "scene strobe_sync", "deck": 1, "beat": 129.0,
            "data": {"scene": "strobe_sync", "reason": "drop_crossing"},
        }
        struct = time.localtime(ts)
        expected_time = f"{struct.tm_hour:02d}:{struct.tm_min:02d}:{struct.tm_sec:02d}.5"
        expected = (
            expected_time + "  "
            + "D1".ljust(bridge_view._DECK_WIDTH) + "  "
            + "laser".ljust(bridge_view._SURFACE_WIDTH) + "  "
            + "scene strobe_sync"
            + " (drop_crossing)"
            + " @b129.0"
        )
        segments = bridge_view.format_line(rec, width=200)
        rendered = "".join(text for text, _ in segments)
        self.assertEqual(rendered, expected)

    def test_attr_keys_are_only_dim_or_bright(self) -> None:
        rec = {
            "ts": 1.0, "lvl": "INFO", "cat": "perf.led.look", "src": "led_dispatch_policy",
            "msg": "look drop_wash", "deck": 2, "beat": 64.0,
            "data": {"reason": "drop_snap"},
        }
        segments = bridge_view.format_line(rec, width=200)
        attrs = {attr for _, attr in segments}
        self.assertTrue(attrs <= {"dim", "bright"})

    def test_time_and_reason_and_beat_are_dim(self) -> None:
        rec = {
            "ts": 1.0, "lvl": "INFO", "cat": "perf.deck", "src": "state_manager",
            "msg": "switch 1->2", "deck": 1, "beat": 10.0, "data": {"reason": "fader_top"},
        }
        segments = bridge_view.format_line(rec, width=200)
        # First segment is the timestamp -> dim.
        self.assertEqual(segments[0][1], "dim")
        # Last two segments are the reason and beat -> dim.
        self.assertEqual(segments[-1][1], "dim")
        self.assertEqual(segments[-2][1], "dim")
        self.assertIn("fader_top", segments[-2][0])
        self.assertIn("10.0", segments[-1][0])

    def test_deck_and_surface_and_value_are_bright(self) -> None:
        rec = {"ts": 1.0, "lvl": "INFO", "cat": "perf.deck", "src": "state_manager",
               "msg": "switch 1->2", "deck": 1}
        segments = bridge_view.format_line(rec, width=200)
        bright_texts = "".join(text for text, attr in segments if attr == "bright")
        self.assertIn("D1", bright_texts)
        self.assertIn("deck", bright_texts)
        self.assertIn("switch 1->2", bright_texts)

    def test_deck_column_blank_padded_when_absent(self) -> None:
        rec = {"ts": 1.0, "lvl": "INFO", "cat": "sys.boot", "src": "bridge", "msg": "bridge log opened"}
        segments = bridge_view.format_line(rec, width=200)
        # segments[2] is the deck field (time, sep, deck, sep, surface, ...):
        # blank-padded (not omitted) when absent, so surface still starts at
        # a fixed offset regardless of whether a line carries a deck (rule 3).
        deck_field_text, deck_field_attr = segments[2]
        self.assertEqual(deck_field_text.strip(), "")
        self.assertEqual(len(deck_field_text), bridge_view._DECK_WIDTH)

    def test_friendly_name_used_for_known_cat(self) -> None:
        rec = {"ts": 1.0, "lvl": "INFO", "cat": "perf.autoloop", "src": "autoloop_controller", "msg": "arm"}
        segments = bridge_view.format_line(rec, width=200)
        rendered = "".join(text for text, _ in segments)
        self.assertIn("autoloop", rendered)

    def test_unmapped_cat_falls_back_to_raw_cat_verbatim(self) -> None:
        rec = {"ts": 1.0, "lvl": "INFO", "cat": "totally.unknown.category", "src": "x", "msg": "hi"}
        segments = bridge_view.format_line(rec, width=200)
        rendered = "".join(text for text, _ in segments)
        self.assertIn("totally.unknown.category", rendered)

    def test_no_reason_segment_when_absent(self) -> None:
        rec = {"ts": 1.0, "lvl": "INFO", "cat": "perf.deck", "src": "state_manager", "msg": "switch"}
        segments = bridge_view.format_line(rec, width=200)
        rendered = "".join(text for text, _ in segments)
        self.assertNotIn("(", rendered)

    def test_no_beat_segment_when_absent(self) -> None:
        rec = {"ts": 1.0, "lvl": "INFO", "cat": "perf.deck", "src": "state_manager", "msg": "switch"}
        segments = bridge_view.format_line(rec, width=200)
        rendered = "".join(text for text, _ in segments)
        self.assertNotIn("@b", rendered)

    def test_truncates_long_line_with_ellipsis_never_wraps(self) -> None:
        rec = {
            "ts": 1.0, "lvl": "INFO", "cat": "perf.led.palette", "src": "led_color_engine",
            "msg": "x" * 200,
        }
        segments = bridge_view.format_line(rec, width=40)
        total_len = sum(len(text) for text, _ in segments)
        self.assertEqual(total_len, 40)
        self.assertEqual(segments[-1][0], "…")

    def test_short_line_is_not_padded_to_width(self) -> None:
        rec = {"ts": 1.0, "lvl": "INFO", "cat": "sys.boot", "src": "bridge", "msg": "hi"}
        segments = bridge_view.format_line(rec, width=200)
        rendered = "".join(text for text, _ in segments)
        self.assertLess(len(rendered), 200)


class TruncateSegmentsTest(unittest.TestCase):
    def test_width_zero_or_negative_returns_empty(self) -> None:
        self.assertEqual(bridge_view._truncate_segments([("abc", "dim")], 0), [])
        self.assertEqual(bridge_view._truncate_segments([("abc", "dim")], -5), [])

    def test_width_one_returns_only_ellipsis(self) -> None:
        result = bridge_view._truncate_segments([("abcdef", "dim")], 1)
        self.assertEqual(result, [("…", "dim")])

    def test_exact_fit_no_truncation(self) -> None:
        segments = [("abc", "dim"), ("de", "bright")]
        result = bridge_view._truncate_segments(segments, 5)
        self.assertEqual(result, segments)

    def test_one_char_over_triggers_truncation(self) -> None:
        segments = [("abcdef", "dim")]
        result = bridge_view._truncate_segments(segments, 5)
        rendered = "".join(t for t, _ in result)
        self.assertEqual(rendered, "abcd…")

    def test_cuts_mid_segment_and_appends_ellipsis(self) -> None:
        segments = [("hello", "dim"), ("world", "bright")]
        result = bridge_view._truncate_segments(segments, 7)
        rendered = "".join(t for t, _ in result)
        self.assertEqual(rendered, "hellowo"[:6] + "…")
        self.assertEqual(len(rendered), 7)


class FormatAgeTest(unittest.TestCase):
    def test_under_one_second_is_just_now(self) -> None:
        self.assertEqual(bridge_view.format_age(100.0, now=100.4), "just now")

    def test_seconds(self) -> None:
        self.assertEqual(bridge_view.format_age(100.0, now=105.0), "5s ago")

    def test_seconds_boundary_59(self) -> None:
        self.assertEqual(bridge_view.format_age(0.0, now=59.0), "59s ago")

    def test_minutes_boundary_60_seconds(self) -> None:
        self.assertEqual(bridge_view.format_age(0.0, now=60.0), "1m ago")

    def test_minutes(self) -> None:
        self.assertEqual(bridge_view.format_age(0.0, now=125.0), "2m ago")

    def test_minutes_boundary_59(self) -> None:
        self.assertEqual(bridge_view.format_age(0.0, now=3599.0), "59m ago")

    def test_hours_boundary_3600_seconds(self) -> None:
        self.assertEqual(bridge_view.format_age(0.0, now=3600.0), "1h ago")

    def test_hours_boundary_23(self) -> None:
        self.assertEqual(bridge_view.format_age(0.0, now=23 * 3600.0), "23h ago")

    def test_days_boundary_24h(self) -> None:
        self.assertEqual(bridge_view.format_age(0.0, now=24 * 3600.0), "1d ago")

    def test_days(self) -> None:
        self.assertEqual(bridge_view.format_age(0.0, now=3 * 86400.0), "3d ago")

    def test_clock_skew_future_ts_clamps_to_just_now(self) -> None:
        self.assertEqual(bridge_view.format_age(200.0, now=100.0), "just now")

    def test_now_defaults_to_current_time_when_omitted(self) -> None:
        self.assertEqual(bridge_view.format_age(time.time()), "just now")


class ParseFilterTest(unittest.TestCase):
    def test_empty_string(self) -> None:
        self.assertEqual(bridge_view.parse_filter(""), {"substring": "", "deck": None, "cat_prefix": ""})

    def test_plain_substring_only(self) -> None:
        result = bridge_view.parse_filter("midi")
        self.assertEqual(result["substring"], "midi")
        self.assertIsNone(result["deck"])
        self.assertEqual(result["cat_prefix"], "")

    def test_deck_token(self) -> None:
        result = bridge_view.parse_filter("deck=2")
        self.assertEqual(result["deck"], 2)
        self.assertEqual(result["substring"], "")

    def test_cat_prefix_token(self) -> None:
        result = bridge_view.parse_filter("cat=perf.laser")
        self.assertEqual(result["cat_prefix"], "perf.laser")

    def test_combined_tokens(self) -> None:
        result = bridge_view.parse_filter("deck=1 cat=health. degraded")
        self.assertEqual(result["deck"], 1)
        self.assertEqual(result["cat_prefix"], "health.")
        self.assertEqual(result["substring"], "degraded")

    def test_multi_word_substring_preserved(self) -> None:
        result = bridge_view.parse_filter("laser fired")
        self.assertEqual(result["substring"], "laser fired")

    def test_invalid_deck_value_becomes_substring_text(self) -> None:
        result = bridge_view.parse_filter("deck=notanumber")
        self.assertIsNone(result["deck"])
        self.assertEqual(result["substring"], "deck=notanumber")


class FilterMatchesTest(unittest.TestCase):
    def test_empty_filter_matches_everything(self) -> None:
        filt = bridge_view.parse_filter("")
        self.assertTrue(bridge_view.filter_matches(filt, {"cat": "anything", "msg": "anything", "deck": 9}))

    def test_deck_mismatch_excludes(self) -> None:
        filt = bridge_view.parse_filter("deck=1")
        self.assertFalse(bridge_view.filter_matches(filt, {"deck": 2}))

    def test_deck_match_includes(self) -> None:
        filt = bridge_view.parse_filter("deck=1")
        self.assertTrue(bridge_view.filter_matches(filt, {"deck": 1}))

    def test_cat_prefix_mismatch_excludes(self) -> None:
        filt = bridge_view.parse_filter("cat=perf.laser")
        self.assertFalse(bridge_view.filter_matches(filt, {"cat": "perf.led.look"}))

    def test_cat_prefix_match_includes(self) -> None:
        filt = bridge_view.parse_filter("cat=perf.laser")
        self.assertTrue(bridge_view.filter_matches(filt, {"cat": "perf.laser.scene"}))

    def test_substring_matches_cat_case_insensitive(self) -> None:
        filt = bridge_view.parse_filter("LASER")
        self.assertTrue(bridge_view.filter_matches(filt, {"cat": "perf.laser.scene", "msg": ""}))

    def test_substring_matches_msg_case_insensitive(self) -> None:
        filt = bridge_view.parse_filter("degraded")
        self.assertTrue(bridge_view.filter_matches(filt, {"cat": "health.midi", "msg": "DEGRADED port=IAC1"}))

    def test_substring_no_match_excludes(self) -> None:
        filt = bridge_view.parse_filter("nonexistent")
        self.assertFalse(bridge_view.filter_matches(filt, {"cat": "perf.deck", "msg": "switch"}))

    def test_combined_filter_requires_all_clauses(self) -> None:
        filt = bridge_view.parse_filter("deck=1 cat=perf. switch")
        self.assertTrue(bridge_view.filter_matches(filt, {"deck": 1, "cat": "perf.deck", "msg": "switch 1->2"}))
        self.assertFalse(bridge_view.filter_matches(filt, {"deck": 2, "cat": "perf.deck", "msg": "switch 1->2"}))
        self.assertFalse(bridge_view.filter_matches(filt, {"deck": 1, "cat": "health.midi", "msg": "switch"}))
        self.assertFalse(bridge_view.filter_matches(filt, {"deck": 1, "cat": "perf.deck", "msg": "no match here"}))


class LatchStateTest(unittest.TestCase):
    def test_warning_latches_and_returns_true_once(self) -> None:
        latch = bridge_view.LatchState()
        rec = {"cat": "state_manager", "lvl": "WARNING", "msg": "event-late"}
        self.assertTrue(latch.note(rec))
        self.assertFalse(latch.note(rec))
        self.assertFalse(latch.is_quiet())

    def test_repeat_warning_same_category_updates_stored_record(self) -> None:
        latch = bridge_view.LatchState()
        latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded: send_error"})
        latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded: port_unavailable"})
        self.assertEqual(len(latch.latched), 1)
        self.assertEqual(latch.latched[0]["msg"], "degraded: port_unavailable")

    def test_health_warning_latches(self) -> None:
        latch = bridge_view.LatchState()
        self.assertTrue(latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded"}))
        self.assertFalse(latch.is_quiet())

    def test_health_info_same_category_clears_latch_and_returns_false(self) -> None:
        latch = bridge_view.LatchState()
        latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded"})
        result = latch.note({"cat": "health.midi", "lvl": "INFO", "msg": "recovered", "ts": 500.0})
        self.assertFalse(result)
        self.assertTrue(latch.is_quiet())

    def test_health_info_different_category_is_noop(self) -> None:
        latch = bridge_view.LatchState()
        latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded"})
        latch.note({"cat": "health.dmx", "lvl": "INFO", "msg": "recovered"})
        self.assertEqual(len(latch.latched), 1)
        self.assertEqual(latch.latched[0]["cat"], "health.midi")

    def test_non_health_warning_has_no_auto_recovery(self) -> None:
        latch = bridge_view.LatchState()
        latch.note({"cat": "state_manager", "lvl": "ERROR", "msg": "boom"})
        latch.note({"cat": "state_manager", "lvl": "INFO", "msg": "all fine now"})
        self.assertEqual(len(latch.latched), 1)
        self.assertFalse(latch.is_quiet())

    def test_ack_clears_everything_regardless_of_category(self) -> None:
        latch = bridge_view.LatchState()
        latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded"})
        latch.note({"cat": "state_manager", "lvl": "ERROR", "msg": "boom"})
        latch.ack()
        self.assertTrue(latch.is_quiet())
        self.assertEqual(latch.latched, [])

    def test_ack_updates_quiet_since_to_now(self) -> None:
        latch = bridge_view.LatchState()
        latch.note({"cat": "state_manager", "lvl": "ERROR", "msg": "boom"})
        latch.ack(now=12345.0)
        self.assertEqual(latch.quiet_since, 12345.0)

    def test_quiet_since_updates_on_last_recovery_clearing_to_empty(self) -> None:
        latch = bridge_view.LatchState()
        latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded"})
        latch.note({"cat": "health.midi", "lvl": "INFO", "msg": "recovered", "ts": 999.0})
        self.assertEqual(latch.quiet_since, 999.0)

    def test_quiet_since_unchanged_while_still_latched(self) -> None:
        latch = bridge_view.LatchState()
        initial = latch.quiet_since
        latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded"})
        latch.note({"cat": "health.dmx", "lvl": "WARNING", "msg": "degraded", "ts": 999.0})
        # health.midi is still latched, so nothing has "become empty" yet.
        self.assertEqual(latch.quiet_since, initial)

    def test_quiet_since_only_updates_on_transition_to_fully_empty(self) -> None:
        latch = bridge_view.LatchState()
        latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded"})
        latch.note({"cat": "health.dmx", "lvl": "WARNING", "msg": "degraded"})
        initial = latch.quiet_since
        # Clearing one of two latched categories: still not "all quiet".
        latch.note({"cat": "health.midi", "lvl": "INFO", "msg": "recovered", "ts": 111.0})
        self.assertEqual(latch.quiet_since, initial)
        self.assertFalse(latch.is_quiet())

    def test_is_quiet_true_initially(self) -> None:
        latch = bridge_view.LatchState()
        self.assertTrue(latch.is_quiet())

    def test_latched_property_returns_all_current_entries(self) -> None:
        latch = bridge_view.LatchState()
        latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "a"})
        latch.note({"cat": "health.dmx", "lvl": "WARNING", "msg": "b"})
        cats = {rec["cat"] for rec in latch.latched}
        self.assertEqual(cats, {"health.midi", "health.dmx"})

    def test_multiple_categories_latch_independently(self) -> None:
        latch = bridge_view.LatchState()
        latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "a"})
        latch.note({"cat": "health.dmx", "lvl": "WARNING", "msg": "b"})
        latch.note({"cat": "health.midi", "lvl": "INFO", "msg": "recovered"})
        self.assertEqual(len(latch.latched), 1)
        self.assertEqual(latch.latched[0]["cat"], "health.dmx")

    def test_debug_or_info_non_health_record_never_latches(self) -> None:
        latch = bridge_view.LatchState()
        self.assertFalse(latch.note({"cat": "state_manager", "lvl": "DEBUG", "msg": "noise"}))
        self.assertFalse(latch.note({"cat": "state_manager", "lvl": "INFO", "msg": "noise"}))
        self.assertTrue(latch.is_quiet())

    def test_bell_signal_false_for_recovery_and_repeat_and_noop(self) -> None:
        latch = bridge_view.LatchState()
        self.assertTrue(latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded"}))
        self.assertFalse(latch.note({"cat": "health.midi", "lvl": "WARNING", "msg": "degraded again"}))
        self.assertFalse(latch.note({"cat": "health.midi", "lvl": "INFO", "msg": "recovered"}))
        self.assertFalse(latch.note({"cat": "health.midi", "lvl": "INFO", "msg": "noop, not latched"}))


class ArgParserTest(unittest.TestCase):
    def test_default_path_is_none(self) -> None:
        args = bridge_view.build_arg_parser().parse_args([])
        self.assertIsNone(args.path)

    def test_path_override_parsed(self) -> None:
        args = bridge_view.build_arg_parser().parse_args(["--path", "/tmp/example.jsonl"])
        self.assertEqual(args.path, "/tmp/example.jsonl")


if __name__ == "__main__":
    unittest.main()

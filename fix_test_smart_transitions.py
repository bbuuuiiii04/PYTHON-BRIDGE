with open('tests/test_smart_transitions.py', 'r') as f:
    content = f.read()

# Add _smart_breakdown_tick to imports
content = content.replace('_smart_drop_tick,', '_smart_drop_tick,\n    _smart_breakdown_tick,')

# Replace SmartBreakdownTests
old_class = """class SmartBreakdownTests(unittest.TestCase):
    def setUp(self):
        self.sm, self.out, self.live_bpm, self.pos_cache = _setup_sm()
        self.sm._smart_rearm_experiment = True
        self.sm._smart_drop_enabled = True
        self.sm._smart_breakdown_enabled = True
        
        self.meta = TrackMetadata()
        self.meta.beatgrid_times_ms = [i * 500.0 for i in range(120)]
        self.meta.smart_breakdowns = [32]
        self.meta.smart_drops = [64]
        
        self.sm._deck[1].meta = self.meta
        self.sm._os.active_deck = 1
        self.sm._os.lighting_mode = "autoloop"

    def test_breakdown_cuts_and_restores(self):
        # Tick before breakdown
        _push_tick(self.sm, this_beat=30)
        self.assertFalse(self.sm._os.breakdown_active)
        self.out.clear_calls()
        
        # Tick on breakdown beat
        _push_tick(self.sm, this_beat=32)
        self.assertTrue(self.sm._os.breakdown_active)
        self.assertEqual(self.sm._os.breakdown_restore_beat, 64)
        
        # Verify deck clear and loop off sent to all decks
        self.assertTrue(any(c[0] == "deck_clear" and c[1][0] == 1 for c in self.out.calls))
        self.assertTrue(any(c[0] == "loop_off" and c[1][0] == 1 for c in self.out.calls))
        self.out.clear_calls()
        
        # Tick inside breakdown
        _push_tick(self.sm, this_beat=40)
        self.assertTrue(self.sm._os.breakdown_active)
        self.out.clear_calls()
        
        # Tick on restore beat
        _push_tick(self.sm, this_beat=64)
        self.assertFalse(self.sm._os.breakdown_active)
        
        # Verify rearm sent
        self.assertTrue(any(c[0] == "deck_load" and c[1][0] == 1 for c in self.out.calls))
        self.assertTrue(any(c[0] == "play_on" and c[1][0] == 1 for c in self.out.calls))"""

new_class = """class SmartBreakdownTests(unittest.TestCase):
    def test_breakdown_cuts_and_restores(self):
        sm = _sm()
        sm._deck[1].meta.smart_breakdowns = [32]
        sm._deck[1].meta.smart_drops = [64]
        sm._smart_breakdown_enabled = True
        
        # Tick before breakdown
        _smart_breakdown_tick(sm, 1, 2, 130.0, 30, 15_000)
        self.assertFalse(sm._os.breakdown_active)
        
        # Tick on breakdown beat
        _smart_breakdown_tick(sm, 1, 2, 130.0, 32, 16_000)
        self.assertTrue(sm._os.breakdown_active)
        self.assertEqual(sm._os.breakdown_restore_beat, 64)
        self.assertEqual(sm._out.send_deck_clear.call_count, 4)
        self.assertEqual(sm._out.send_loop_off.call_count, 4)
        
        # Tick inside breakdown
        _smart_breakdown_tick(sm, 1, 2, 130.0, 40, 20_000)
        self.assertTrue(sm._os.breakdown_active)
        
        # Tick on restore beat
        _smart_breakdown_tick(sm, 1, 2, 130.0, 64, 32_000)
        self.assertFalse(sm._os.breakdown_active)
        sm._send_autoloop_deck_load.assert_called_once()"""

content = content.replace(old_class, new_class)

with open('tests/test_smart_transitions.py', 'w') as f:
    f.write(content)

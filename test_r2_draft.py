import sys
from pathlib import Path
sys.path.insert(0, str(Path('/Users/bbui')))
from rb_ss_bridge_v2.tests.test_laser_executor_lifecycle import _make_config, _FakeMidiOutput, _ctx, _decision, _scene
from rb_ss_bridge_v2.laser_executor import LaserSceneExecutor
from rb_ss_bridge_v2.laser_models import LaserPersonality

scenes = {
    "d1": _scene("d1", note=41),
    "safe_static": _scene("safe_static", scene_type="static", note=99),
}
config_on = _make_config(scenes)
config_on.smart_drop_mode = "blackout_mask"
config_off = _make_config(scenes)
config_off.smart_drop_mode = "scene"

personality = LaserPersonality(
    name="test", safe_scene="safe_static", default_scene="d1",
    phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
    drop_scene="d1", post_drop_scene="",
    breakdown_scene="d1", transition_scene="safe_static",
    drop_bank=("d1",),
    drop_lifecycle_mirror=True,
)

backend_on = _FakeMidiOutput()
ex_on = LaserSceneExecutor(config_on, backend_on, personality, randomize_cursors=False)
ctx_on = _ctx()
ctx_on.smart_drop_blackout_arm = True
ex_on.on_decision(_decision("d1", "drop_crossing", "drop"), ctx_on)
print("ON calls:")
for msg, prio in backend_on.calls:
    print(f"kind={msg.kind} ch={msg.channel} note={msg.note} vel={msg.velocity}")

backend_off = _FakeMidiOutput()
ex_off = LaserSceneExecutor(config_off, backend_off, personality, randomize_cursors=False)
ctx_off = _ctx()
ctx_off.smart_drop_blackout_arm = True
ex_off.on_decision(_decision("d1", "drop_crossing", "drop"), ctx_off)
print("OFF calls:")
for msg, prio in backend_off.calls:
    print(f"kind={msg.kind} ch={msg.channel} note={msg.note} vel={msg.velocity}")


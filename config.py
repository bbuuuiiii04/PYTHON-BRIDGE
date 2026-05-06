"""Central constants for rb_ss_bridge_v2."""
from pathlib import Path

# ── OS2L / SoundSwitch ───────────────────────────────────────────────────────
OS2L_FALLBACK_HOST = "127.0.0.1"
OS2L_FALLBACK_PORT = 58716
AUTOLOOP_BEATS = 8
AUTOLOOP_ARM_PHRASE_BEATS = 32

# ── TimecodeLink ─────────────────────────────────────────────────────────────
TL_LOG_PATH = Path(
    "~/Library/Application Support/TimecodeLink/timecodelink.log"
).expanduser()
TL_PLAYLIST_PATH = Path(
    "~/Library/Application Support/TimecodeLink/playlist.yaml"
).expanduser()

# ── RB Direct Memory (arm64, RB 7.2.11) ─────────────────────────────────────
# All offsets are from the TEXT segment load base (post-ASLR).
# Confirmed working in session 30 against RB 7.2.11 pid 78757 base 0x100594000.
RB_SCALE         = 0.022675736961451247   # 1/44100 — samples to ms
RB_GLOBAL_OFF    = 0x4DBC6D0  # base + this → ptr to DjEngineIF-like container
RB_DECK1_OFF     = 0x478      # container[+this] → DPU1 ptr
RB_DECK2_OFF     = 0x480      # container[+this] → DPU2 ptr
RB_INNER_OFF     = 0x8        # DPU[+this] → inner ptr
RB_INNER_LEN_OFF = 0x8        # inner[+this]: bits[32..63] = track length samples
RB_POS_OFF       = 0xC        # inner[+this] as i32 → position samples
RB_SEC_OFF       = 0x60       # inner[+this] → secondary ptr
RB_PLAY_OFF      = 0x2F0      # secondary[+this] as i32: <0 → playing (mode 272)
RB_DDJ_OFF       = 0x312      # secondary[+this] byte: non-zero → DDJ mode (4112/4368)

RB_DECK_OFFS = {1: RB_DECK1_OFF, 2: RB_DECK2_OFF}

# DjPlayUnit vtable offset (from base) — used to locate DPU2 by forward scan from DPU1.
# Confirmed stable across 3 ASLR sessions (pid 53932/70582/73419, bases 0x1022e8000/0x102218000/0x104ce4000).
RB_DPU_VTABLE_OFF  = 0x4ace898
# Max bytes to scan forward from DPU1 when locating DPU2. Seen strides: 0x70 (session 2), 0x150 (session 3).
RB_DPU_SCAN_WINDOW = 0x400

# ── Outer struct (direct deck-position chain) ────────────────────────────────
# Discovered via structural heap scan (Codex probe, confirmed live).
# outer + OUTER_INNER1_OFF → inner1 → [+RB_POS_OFF] = deck 1 samples
# outer + OUTER_INNER2_OFF → inner2 → [+RB_POS_OFF] = deck 2 samples
# The correct deck-2 inner is reached ONLY via this outer chain.
# container+0x480 and the Phase-3 DPU slot scan reach a static/stub object.
OUTER_INNER1_OFF      = 0x08   # outer[+this] → inner1 ptr (ObjC heap)
OUTER_INNER2_OFF      = 0x78   # outer[+this] → inner2 ptr (ObjC heap)
# Fast-path hint: in one confirmed session, container − outer = 0x270.
# Not proven across restarts — always validate before trusting.
OUTER_FAST_PATH_DELTA = 0x270
# PROVEN UNSTABLE: inner1/inner2 are independent ObjC allocations with no fixed offset.
# Offsets observed: +0x4e0 (Codex probe), -0x7570 (restart 2). Do NOT use as fast path.
# Kept for documentation only.
DECK2_INNER1_DELTA    = 0x4e0

# ── Memory reader ────────────────────────────────────────────────────────────
MEM_POLL_HZ        = 60
MEM_MAX_ELAPSED_MS = 7_200_000   # sanity cap: 2 h
MEM_STALE_S        = 3.0         # treat position as stale after this many seconds

# ── OSC ──────────────────────────────────────────────────────────────────────
OSC_LISTEN_PORT = 7001

# ── lsof / track identification ──────────────────────────────────────────────
AUDIO_EXTS           = frozenset({'.mp3', '.m4a', '.flac', '.wav', '.aif', '.aiff', '.ogg', '.opus'})
LSOF_LEN_TOLERANCE_MS = 1_000   # ±1 s for track-length matching
LSOF_COOLDOWN_S      = 2.0      # min seconds between lsof runs per deck

# ── Timing and guards ────────────────────────────────────────────────────────
TIMING_COMPENSATION_MS = 0
STOP_DEBOUNCE_S        = 0.5    # confirm stop after playing=False for this long
ARM_GUARD_S            = 3.0    # suppress stop-detection after arm or deck switch
PLAY_SETTLE_MS         = 400    # delay before flash-arm after resume (BPM settle)

# ── BPM send thresholds ──────────────────────────────────────────────────────
BPM_THRESHOLD_UNSCRIPTED = 0.1  # send get_bpm when change exceeds this (autoloop)
BPM_THRESHOLD_SCRIPTED   = 2.0  # larger threshold for scripted shows (prevent jitter)

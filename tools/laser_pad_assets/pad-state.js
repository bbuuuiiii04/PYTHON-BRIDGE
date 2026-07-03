const ROLE_FIELDS = {
  groove: ['phrase_scene', 'phrase_bank'],
  buildup: ['buildup_scene', 'buildup_bank'],
  drop: ['drop_scene', 'drop_bank'],
  post_drop: ['post_drop_scene', 'post_drop_bank'],
  breakdown: ['breakdown_scene', 'breakdown_bank'],
};

const BANK_ROLES = [
  { key: 'groove', label: 'Groove (phrase)' },
  { key: 'buildup', label: 'Buildup' },
  { key: 'drop', label: 'Drop' },
  { key: 'post_drop', label: 'Post-drop' },
  { key: 'breakdown', label: 'Breakdown' },
];

// Curated palette for personality chips. Six visually distinct hues that
// stay readable on the dark pad-grid background. Auto-assigned in
// alphabetical order to personalities that don't have an explicit override
// stored in _pad_meta.personality_colors[<name>].color.
const PERSONALITY_COLOR_PALETTE = [
  '#06b6d4', // cyan
  '#d946ef', // magenta
  '#f59e0b', // amber
  '#84cc16', // lime
  '#8b5cf6', // violet
  '#fb7185', // coral
];

function hardDuplicateMap(config) {
  const byKey = new Map();
  const personalities = config.personalities || {};
  const scenes = config.scenes || {};
  Object.entries(personalities).forEach(([personality, pdata]) => {
    if (!pdata || typeof pdata !== 'object') return;
    Object.entries(ROLE_FIELDS).forEach(([role, [sceneField, bankField]]) => {
      const names = [];
      const primary = pdata[sceneField];
      if (typeof primary === 'string' && primary) names.push(primary);
      const bank = Array.isArray(pdata[bankField]) ? pdata[bankField] : [];
      bank.forEach((sceneName) => {
        if (typeof sceneName === 'string' && sceneName && !names.includes(sceneName)) {
          names.push(sceneName);
        }
      });
      names.forEach((sceneName) => {
        const midi = (scenes[sceneName] || {}).midi || {};
        if (typeof midi.note !== 'number') return;
        const channel = typeof midi.channel === 'number' ? midi.channel : 1;
        const key = `${channel}:${midi.note}`;
        if (!byKey.has(key)) byKey.set(key, []);
        byKey.get(key).push({ personality, role, sceneName });
      });
    });
  });
  return byKey;
}

window.LaserPad = window.LaserPad || {};

(function laserPadState(ns) {
  ns.ROLE_FIELDS = ROLE_FIELDS;
  ns.BANK_ROLES = BANK_ROLES;
  ns.PERSONALITY_COLOR_PALETTE = PERSONALITY_COLOR_PALETTE;
  ns.hardDuplicateMap = hardDuplicateMap;

  ns.state = {
    createInitialState() {
      return {
    loading: true,

    config: {},

    liveErrors: [],

    liveWarnings: [],

    hardDuplicates: [],

    softDuplicates: [],

    midiPorts: [],

    selectedPort: '',

    manualPort: '',

    manualPortOpen: false,

    draftDryRun: true,

    timingDraft: {
      phrase_interval_beats: 32,
      minimum_scene_hold_beats: 8,
      buildup_lookahead_beats: 32,
      pre_drop_blackout_beats: 4,
      post_drop_hold_beats: 8,
      breakdown_default_restore_beats: 64,
    },

    aliasesDraft: { text: '' },

    bpmBandDraft: { min: 0, max: 0 },

    resolverTest: {
      playlist: '',
      bpm: '',
      loading: false,
      result: null,
      error: '',
    },

    activeBankId: 'bank_1',

    test: { channel: 1, note: 60, velocity: 127, behavior: 'pulse', duration_ms: 100, hold_beats: 4, bpm: 128 },

    statusText: '',

    currentConfigHash: '',

    lastCommittedHash: '',

    saveState: { kind: 'saved', timestamp: '', lastError: '' },

    modal: {
      open: false,
      type: 'confirm',
      title: '',
      message: '',
      fields: [],
      error: '',
      confirmText: 'Confirm',
      cancelText: 'Cancel',
      danger: false,
      validate: null,
    },

    modalResolver: null,

    runtime: { active_personality: '', current_scene: '', last_reason: '', stale_seconds: 0, available: false, enabled: false, emergency: false },

    runtimeTimer: null,

    beforeUnloadHandler: null,

    firingNote: null,

    firingTimer: null,

    touchLongPressTimer: null,

    bankLongPressTimer: null,

    touchLongPressed: false,

    pressProgress: { note: null, startedAt: 0 },

    suppressClickNote: null,

    duplicateWarning: '',

    openNote: null,

    draftTimer: null,

    draggedNote: null,

    dropTargetNote: null,

    showVerifyPanel: false,

    validateResults: { errors: [], warnings: [] },

    verifyResults: { checks: [] },

    verifyByNote: {},

    lastReassignUndo: {
      visible: false,
      message: '',
      patch: null,
      timer: null,
    },

    historyOpen: false,

    historyLoading: false,

    historyItems: [],

    historySelected: null,

    historyDiff: '',

    settingsOpen: false,

    settingsActiveTab: 'global',

    accessOpen: false,

    accessInfo: null,

    accessQrSvg: '',

    settingsTabs: [
      { id: 'global', label: 'Global' },
      { id: 'personalities', label: 'Personalities' },
      { id: 'blackout', label: 'Blackout' },
      { id: 'banks', label: 'Banks' },
    ],

    blackoutForm: {
      on: { channel: 1, note: 0, velocity: 127, duration_ms: 80 },
      off: { channel: 1, note: 1, velocity: 127, duration_ms: 80 },
    },

    overwriteDialog: {
      open: false,
      sourceNote: null,
      targetNote: null,
      pending: null,
    },

    drawer: {
      personality: 'house',
      role: 'groove',
      behavior: 'pulse',
      velocity: 127,
      hold_beats: 4,
      duration_ms: 80,
      cooldown_beats: 16,
      immediate: false,
      safety_class: 'movement_low',
      label: '',
      source_behavior: 'pulse',
      behaviorTouched: false,
      system: false,
    },

    _selectorCache: new Map(),
    _draftQueues: new Map(),
      };
    },
  };
})(window.LaserPad);

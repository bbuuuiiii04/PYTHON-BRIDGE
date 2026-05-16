function hardDuplicateMap(config) {
  const byKey = new Map();
  const personalities = config.personalities || {};
  const scenes = config.scenes || {};
  Object.entries(personalities).forEach(([personality, pdata]) => {
    if (!pdata || typeof pdata !== 'object') return;
    const roleMap = {
      groove: ['phrase_scene', 'phrase_bank'],
      buildup: ['buildup_scene', 'buildup_bank'],
      drop: ['drop_scene', 'drop_bank'],
      post_drop: ['post_drop_scene', 'post_drop_bank'],
      breakdown: ['breakdown_scene', 'breakdown_bank'],
    };
    Object.entries(roleMap).forEach(([role, [sceneField, bankField]]) => {
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

window.laserPadApp = function laserPadApp() {
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
    draftDryRun: true,
    timingDraft: {
      phrase_interval_beats: 32,
      minimum_scene_hold_beats: 8,
      buildup_lookahead_beats: 32,
    },
    activeBankId: 'bank_1',
    test: { channel: 1, note: 60, velocity: 127, behavior: 'pulse', duration_ms: 100, hold_beats: 4, bpm: 128 },
    statusText: '',
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

    async init() {
      await this.refreshConfig();
      await this.refreshMidiPorts();
      await this.refreshRuntimeStatus();
      this.startRuntimeTimer();
      this.loading = false;
    },

    startRuntimeTimer() {
      this.stopRuntimeTimer();
      this.runtimeTimer = setInterval(() => {
        this.refreshRuntimeStatus();
      }, 1000);
      if (typeof window !== 'undefined') {
        this.beforeUnloadHandler = () => this.stopRuntimeTimer();
        window.addEventListener('beforeunload', this.beforeUnloadHandler);
      }
    },

    stopRuntimeTimer() {
      if (this.runtimeTimer) {
        clearInterval(this.runtimeTimer);
        this.runtimeTimer = null;
      }
      if (typeof window !== 'undefined' && this.beforeUnloadHandler) {
        window.removeEventListener('beforeunload', this.beforeUnloadHandler);
        this.beforeUnloadHandler = null;
      }
    },

    destroy() {
      this.stopRuntimeTimer();
    },

    async refreshRuntimeStatus() {
      try {
        const response = await fetch('/api/runtime_status');
        const data = await response.json();
        this.runtime = {
          active_personality: String(data.active_personality || ''),
          current_scene: String(data.current_scene || ''),
          last_reason: this.runtimeReasonLabel(data),
          stale_seconds: Number(data.stale_seconds || 0),
          available: Boolean(data.available),
          enabled: Boolean(data.enabled),
          emergency: Boolean(data.emergency),
        };
      } catch (err) {
        this.runtime = { active_personality: '', current_scene: '', last_reason: '', stale_seconds: 0, available: false, enabled: false, emergency: false };
      }
    },

    runtimeReasonLabel(data) {
      const reason = String(data?.last_reason || data?.reason || '');
      if (reason === 'status_file_missing_or_stale') return 'Bridge offline';
      if (reason === 'parse_error') return 'Status unavailable';
      return reason;
    },

    runtimeStatusClass() {
      if (this.runtime?.emergency) return 'runtime-emergency';
      if (this.runtime?.available && this.runtime?.enabled) return 'runtime-live';
      return 'runtime-offline';
    },

    async refreshConfig() {
      try {
        const response = await fetch('/api/config');
        const payload = await response.json();
        this.config = payload.config || {};
        this.liveErrors = payload.errors || [];
        this.liveWarnings = payload.warnings || [];
        this.hardDuplicates = Array.isArray(payload.hard_duplicates) ? payload.hard_duplicates : [];
        this.softDuplicates = Array.isArray(payload.soft_duplicates) ? payload.soft_duplicates : [];
        this.selectedPort = String(this.config?.midi_output_port || this.selectedPort || '');
        this.draftDryRun = Boolean(this.config?.dry_run ?? true);
        this.syncTestUi();
        this.syncTimingDraft();
        if (!this.bankById(this.activeBankId)) {
          this.activeBankId = (this.banks()[0] || {}).id || 'bank_1';
        }
        this.duplicateWarning = this.computeDuplicateWarning();
        if (this.test.note === undefined || this.test.note === null) {
          const first = this.currentNotes()[0];
          this.test.note = first || 0;
        }
      } catch (err) {
        this.statusText = `Config load failed: ${err.message}`;
      }
    },

    banks() {
      const banks = this.config?._pad_meta?.banks;
      return Array.isArray(banks) ? banks : [];
    },

    bankById(bankId) {
      return this.banks().find((bank) => bank.id === bankId) || null;
    },

    currentBank() {
      return this.bankById(this.activeBankId);
    },

    currentNotes() {
      const bank = this.currentBank();
      return Array.isArray(bank?.notes) ? bank.notes : [];
    },

    syncTestUi() {
      const ui = this.config?._pad_meta?.ui || {};
      this.test.bpm = Number(ui.bpm_for_test_fire ?? this.test.bpm ?? 128);
      this.test.velocity = Number(ui.last_test_velocity ?? this.test.velocity ?? 127);
      this.test.hold_beats = Number(ui.last_test_hold_beats ?? this.test.hold_beats ?? 4);
      this.test.channel = Number(ui.last_test_channel ?? this.test.channel ?? 1);
      this.test.note = Number(ui.last_test_note ?? this.test.note ?? 60);
    },

    activePersonality() {
      const selected = this.config?._pad_meta?.ui?.last_personality;
      if (typeof selected === 'string' && selected) {
        return selected;
      }
      return this.config?.default_personality || 'house';
    },

    personalityData() {
      const personalities = this.config?.personalities || {};
      return personalities[this.activePersonality()] || {};
    },

    drawerPersonalityName() {
      if (this.openNote !== null && this.openNote !== undefined && this.drawer.personality) {
        return String(this.drawer.personality);
      }
      return this.activePersonality();
    },

    drawerPersonalityData() {
      const personalities = this.config?.personalities || {};
      return personalities[this.drawerPersonalityName()] || {};
    },

    sceneMetaByNote(note) {
      return this.sceneDetailsByNote(note);
    },

    sceneDetailsByNote(note, personalityName = this.activePersonality()) {
      const personalities = this.config?.personalities || {};
      const pdata = personalities[personalityName] || {};
      const scenes = this.config?.scenes || {};
      const bankChannel = Number(this.currentBank()?.channel || 1);
      const manual = this.config?.manual_commands || {};

      for (const slot of ['blackout_on', 'blackout_off']) {
        const cmd = manual[slot];
        if (cmd && Number(cmd.channel ?? 1) === bankChannel && Number(cmd.note) === Number(note)) {
          return {
            role: 'blackout',
            sceneName: slot,
            mapped: true,
            primary: true,
            safetyClass: 'blackout',
            label: slot === 'blackout_on' ? 'BLACKOUT ON' : 'BLACKOUT OFF',
            channel: bankChannel,
            personality: '',
            behavior: String(cmd.behavior || 'pulse'),
            velocity: Number(cmd.velocity ?? 127),
            hold_beats: 0,
            duration_ms: Number(cmd.duration_ms ?? 80),
            cooldown_beats: 0,
            immediate: true,
            system: true,
          };
        }
      }

      const roleMap = [
        ['groove', 'phrase_scene', 'phrase_bank'],
        ['buildup', 'buildup_scene', 'buildup_bank'],
        ['drop', 'drop_scene', 'drop_bank'],
        ['post_drop', 'post_drop_scene', 'post_drop_bank'],
        ['breakdown', 'breakdown_scene', 'breakdown_bank'],
      ];

      for (const [role, sceneField, bankField] of roleMap) {
        const names = [];
        if (typeof pdata[sceneField] === 'string' && pdata[sceneField]) {
          names.push(pdata[sceneField]);
        }
        const bank = Array.isArray(pdata[bankField]) ? pdata[bankField] : [];
        bank.forEach((sceneName) => {
          if (typeof sceneName === 'string' && sceneName && !names.includes(sceneName)) {
            names.push(sceneName);
          }
        });
        for (const sceneName of names) {
          const scene = scenes[sceneName] || {};
          const midi = scene.midi || {};
          const midiChannel = Number(midi.channel ?? 1);
          if (Number(midi.note) === Number(note) && midiChannel === bankChannel) {
            return {
              role,
              sceneName,
              mapped: true,
              primary: pdata[sceneField] === sceneName,
              safetyClass: scene.safety_class || 'safe',
              label: scene.label || '',
              channel: midiChannel,
              personality: this.activePersonality(),
              behavior: midi.behavior || 'pulse',
              velocity: Number(midi.velocity ?? 127),
              hold_beats: Number(midi.hold_beats ?? this.currentBank()?.default_hold_beats ?? 4),
              duration_ms: Number(midi.duration_ms ?? this.currentBank()?.default_duration_ms ?? 80),
              cooldown_beats: Number(scene.cooldown_beats ?? this.currentBank()?.default_cooldown_beats ?? 8),
              immediate: Boolean(scene.immediate),
              system: false,
            };
          }
        }
      }

      return {
        role: '',
        sceneName: '',
        mapped: false,
        primary: false,
        safetyClass: 'safe',
        label: this.unmappedLabel(note),
        channel: bankChannel,
        personality: this.activePersonality(),
        behavior: this.currentBank()?.default_behavior || 'pulse',
        velocity: 127,
        hold_beats: Number(this.currentBank()?.default_hold_beats || 4),
        duration_ms: Number(this.currentBank()?.default_duration_ms || 80),
        cooldown_beats: Number(this.currentBank()?.default_cooldown_beats || 8),
        immediate: false,
        system: false,
      };
    },

    unmappedLabel(note) {
      const bank = this.currentBank();
      const channel = bank?.channel || 1;
      return this.config?._pad_meta?.note_labels?.[`${channel}:${note}`] || '';
    },

    displayLabel(note) {
      const meta = this.sceneMetaByNote(note);
      if (!meta.mapped) return String(note);
      if (meta.label) return meta.label;
      if (meta.mapped && meta.role) return `${meta.role} ${note}`;
      return String(note);
    },

    roleClass(note) {
      const role = this.sceneMetaByNote(note).role;
      return role ? `role-${role}` : '';
    },

    roleText(note) {
      const meta = this.sceneMetaByNote(note);
      if (!meta.role) return 'unmapped';
      return meta.primary ? `⭐ ${meta.role}` : meta.role;
    },

    safetyDotClass(note) {
      const safety = this.sceneMetaByNote(note).safetyClass;
      return `dot-${String(safety).replace(/[^a-z_]/g, '_')}`;
    },

    isMapped(note) {
      return this.sceneMetaByNote(note).mapped;
    },

    isFiring(note) {
      return Number(this.firingNote) === Number(note);
    },

    isPressing(note) {
      return Number(this.pressProgress.note) === Number(note);
    },

    channelPill(note) {
      return `Ch${this.sceneMetaByNote(note).channel}`;
    },

    // Tile decoration keys use the bank's channel; verify rows use scene.midi.channel.
    // These must agree, which the pad enforces by mirroring bank.channel into scene.midi.channel
    // whenever a mapping is created/moved. If that invariant ever breaks, verify-fail dots
    // will silently fail to render. See apply_mapping in tools/laser_config_ops.py.
    noteKey(note) {
      return `${Number(this.currentBank()?.channel || 1)}:${Number(note)}`;
    },

    verifyState(note) {
      return this.verifyByNote[this.noteKey(note)] || null;
    },

    noteTitle(note) {
      const meta = this.sceneDetailsByNote(note);
      const state = this.verifyState(note);
      const verifyText = state && state.ok === false ? `verify: ${state.detail}` : '';
      if (!meta.mapped) return verifyText || `note ${note}`;
      const duration = meta.behavior === 'hold_beats'
        ? `${meta.hold_beats} beats`
        : `${meta.duration_ms}ms`;
      return [
        `${meta.sceneName} · ch${meta.channel} · note${note} · ${meta.behavior} ${duration}`,
        verifyText,
      ].filter(Boolean).join('\n');
    },

    cloneMapping(note) {
      const meta = this.sceneDetailsByNote(note);
      if (!meta.mapped || !meta.sceneName) return null;
      const scene = this.config?.scenes?.[meta.sceneName];
      if (!scene || typeof scene !== 'object') return null;
      return {
        sceneName: meta.sceneName,
        midi: JSON.parse(JSON.stringify(scene.midi || {})),
      };
    },

    patchForSnapshot(snapshot) {
      if (!snapshot || !snapshot.sceneName) return {};
      return {
        [snapshot.sceneName]: {
          midi: snapshot.midi,
        },
      };
    },

    computeDuplicateWarning() {
      const serverHard = Array.isArray(this.hardDuplicates)
        ? this.hardDuplicates.filter((row) => Array.isArray(row.refs) && row.refs.length > 1)
        : [];
      if (serverHard.length) {
        const first = serverHard[0];
        return `Duplicate mapping on ${first.channel}:${first.note} across ${first.refs.length} scenes`;
      }
      const hard = hardDuplicateMap(this.config);
      const dupes = Array.from(hard.entries()).filter(([, refs]) => refs.length > 1);
      if (!dupes.length) return '';
      const [key, refs] = dupes[0];
      return `Duplicate mapping on ${key} across ${refs.length} scenes`;
    },

    headerBanner() {
      if (Array.isArray(this.liveErrors) && this.liveErrors.length) {
        return { kind: 'error', text: `${this.liveErrors.length} config error(s): ${this.liveErrors[0]}` };
      }
      if (this.duplicateWarning) {
        const warningSuffix = this.liveWarnings.length ? ` · ${this.liveWarnings[0]}` : '';
        return { kind: 'warn', text: `${this.duplicateWarning}${warningSuffix}` };
      }
      if (Array.isArray(this.liveWarnings) && this.liveWarnings.length) {
        return { kind: 'warn', text: this.liveWarnings[0] };
      }
      return null;
    },

    openDiagnosticsPanel() {
      this.showVerifyPanel = true;
      if (typeof document !== 'undefined') {
        document.querySelector('.result-panels')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    },

    openSettingsTab(tab) {
      this.settingsActiveTab = tab;
      this.openSettingsPanel();
    },

    async validateDraftOnly() {
      try {
        const response = await fetch('/api/validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const data = await response.json();
        const errors = Array.isArray(data.errors) ? data.errors : [];
        const warnings = Array.isArray(data.warnings) ? data.warnings : [];
        this.validateResults = { errors, warnings };
        this.showVerifyPanel = true;
        this.statusText = `Validation: ${errors.length} error(s), ${warnings.length} warning(s)`;
      } catch (err) {
        this.statusText = `Validation failed: ${err.message}`;
      }
    },

    async persistTestUi() {
      const patch = {
        _pad_meta: {
          ui: {
            bpm_for_test_fire: Number(this.test.bpm || 128),
            last_test_channel: Number(this.test.channel || 1),
            last_test_note: Number(this.test.note || 0),
            last_test_velocity: Number(this.test.velocity || 127),
            last_test_hold_beats: Number(this.test.hold_beats || 4),
          },
        },
      };
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Quick test settings save failed';
          return;
        }
        this.statusText = 'Quick test settings saved';
      } catch (err) {
        this.statusText = `Quick test settings save failed: ${err.message}`;
      }
    },

    async fireQuickTest() {
      const channel = Number(this.test.channel || 1);
      const note = Number(this.test.note || 0);
      const meta = this.sceneDetailsByNote(note);
      const mapped = Boolean(meta?.mapped);
      const behavior = String(mapped ? (meta.behavior || 'pulse') : 'pulse');
      const overrides = {
        behavior,
        duration_ms: Number(mapped ? (meta.duration_ms ?? 80) : 80),
        hold_beats: Number(mapped ? (meta.hold_beats ?? this.test.hold_beats ?? 4) : (this.test.hold_beats ?? 4)),
      };
      await this.sendTest(channel, note, overrides);
    },

    async addBankPrompt() {
      const name = window.prompt('Bank name:', `Bank ${this.banks().length + 1}`);
      if (!name || !name.trim()) return;
      const channelRaw = window.prompt('MIDI channel (1-16):', '1');
      if (channelRaw === null) return;
      const channel = Number(channelRaw);
      if (!Number.isFinite(channel) || channel < 1 || channel > 16) {
        this.statusText = 'Channel must be 1-16.';
        return;
      }
      const existingNotes = new Set(this.banks().flatMap((bank) => Array.isArray(bank.notes) ? bank.notes : []));
      const notes = [];
      for (let note = 0; note <= 127; note += 1) {
        if (!existingNotes.has(note) && notes.length < 16) notes.push(note);
      }
      if (!notes.length) {
        this.statusText = 'No unmapped MIDI notes available for a new bank.';
        return;
      }
      const idSeed = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || `bank_${this.banks().length + 1}`;
      let id = idSeed;
      let suffix = 2;
      const ids = new Set(this.banks().map((bank) => bank.id));
      while (ids.has(id)) {
        id = `${idSeed}_${suffix}`;
        suffix += 1;
      }
      const banks = [
        ...this.banks().map((bank) => ({ ...bank, notes: [...(bank.notes || [])] })),
        {
          id,
          name: name.trim(),
          channel,
          notes,
          default_role: 'groove',
          default_behavior: 'pulse',
          default_duration_ms: 80,
          default_safety: 'movement_low',
          default_cooldown_beats: 16,
        },
      ];
      await this.patchBanks(banks, `Added bank ${name.trim()}`);
      this.activeBankId = id;
    },

    editBankPrompt(bankId) {
      const index = this.banks().findIndex((bank) => bank.id === bankId);
      if (index < 0) return;
      const bank = this.banks()[index];
      const name = window.prompt('Bank name:', bank.name || bank.id);
      if (name && name.trim()) {
        this.saveBank(index, 'name', name.trim());
      }
      const channelRaw = window.prompt('MIDI channel (1-16):', String(bank.channel || 1));
      if (channelRaw !== null) {
        this.saveBank(index, 'channel', channelRaw);
      }
    },

    startBankLongPress(bankId) {
      this.cancelBankLongPress();
      this.bankLongPressTimer = setTimeout(() => {
        this.editBankPrompt(bankId);
        this.bankLongPressTimer = null;
      }, 500);
    },

    cancelBankLongPress() {
      if (this.bankLongPressTimer) {
        clearTimeout(this.bankLongPressTimer);
        this.bankLongPressTimer = null;
      }
    },

    async refreshMidiPorts() {
      try {
        const response = await fetch('/api/midi_ports');
        const data = await response.json();
        this.midiPorts = Array.isArray(data.ports) ? data.ports : [];
        if (!this.selectedPort && this.midiPorts.length) {
          this.selectedPort = this.midiPorts[0];
        }
      } catch (err) {
        this.statusText = `MIDI port refresh failed: ${err.message}`;
      }
    },

    availablePorts() {
      const live = Array.isArray(this.midiPorts) ? this.midiPorts : [];
      const configured = String(this.config?.midi_output_port || '').trim();
      const selected = String(this.selectedPort || '').trim();
      const merged = [...live];
      [configured, selected].forEach((name) => {
        if (name && !merged.includes(name)) merged.push(name);
      });
      return merged;
    },

    async applyManualPort() {
      const name = String(this.manualPort || '').trim();
      if (!name) return;
      this.selectedPort = name;
      this.manualPort = '';
      await this.setMidiPort();
    },

    async setMidiPort() {
      if (!this.selectedPort) return;
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch: { midi_output_port: this.selectedPort } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Failed to set MIDI output port';
          return;
        }
        this.statusText = `MIDI output set: ${this.selectedPort}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `MIDI port update failed: ${err.message}`;
      }
    },

    engineStateLabel() {
      if (!this.config) return '';
      if (this.config.enabled && this.config.dry_run) return 'live · dry_run';
      if (this.config.enabled) return 'LIVE · sending MIDI';
      return 'idle (disabled)';
    },

    personalityNames() {
      const personalities = this.config?.personalities || {};
      return Object.keys(personalities).sort();
    },

    availableScenes() {
      const scenes = this.config?.scenes || {};
      return Object.keys(scenes).sort();
    },

    smartDropModes() {
      return ['blackout_mask', 'legacy_rearm'];
    },

    async setSmartDropMode(value) {
      const v = String(value || '').trim();
      if (!v) return;
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch: { smart_drop_mode: v } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Failed to set smart_drop_mode';
          return;
        }
        this.statusText = `smart_drop_mode=${v}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Smart-drop update failed: ${err.message}`;
      }
    },

    async setLifecycleScene(field, value) {
      const key = String(field || '').trim();
      if (!key) return;
      const v = String(value || '');
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch: { [key]: v } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || `Failed to update ${key}`;
          return;
        }
        this.statusText = `${key}=${v || '(none)'}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `${key} update failed: ${err.message}`;
      }
    },

    async setEnabled(enabled) {
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch: { enabled: Boolean(enabled) } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Failed to toggle engine';
          return;
        }
        this.statusText = `enabled=${enabled ? 'true' : 'false'}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Engine toggle failed: ${err.message}`;
      }
    },

    async setDefaultPersonality(name) {
      const value = String(name || '').trim();
      if (!value) return;
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch: { default_personality: value } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Failed to set default personality';
          return;
        }
        this.statusText = `default_personality=${value}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Personality update failed: ${err.message}`;
      }
    },

    async setActivePersonality(name) {
      const value = String(name || '').trim();
      if (!value) return;
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          // /api/draft deep-merges nested dicts; sibling _pad_meta keys are preserved.
          body: JSON.stringify({ patch: { _pad_meta: { ui: { last_personality: value } } } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Failed to set active personality';
          return;
        }
        this.statusText = `active_personality=${value}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Active personality update failed: ${err.message}`;
      }
    },

    async _personalityCRUD(path, body, successMsg) {
      try {
        const response = await fetch(path, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || `Personality op failed`;
          return false;
        }
        this.statusText = successMsg;
        await this.refreshConfig();
        return true;
      } catch (err) {
        this.statusText = `Personality op failed: ${err.message}`;
        return false;
      }
    },

    async createPersonalityPrompt() {
      const name = window.prompt('New personality name:', '');
      if (!name) return;
      await this._personalityCRUD(
        '/api/personality/create',
        { name },
        `Created personality '${name.trim().toLowerCase()}'`
      );
    },

    async renamePersonalityPrompt(oldName) {
      const next = window.prompt(`Rename '${oldName}' to:`, oldName);
      if (!next) return;
      const trimmed = next.trim();
      if (!trimmed || trimmed.toLowerCase() === oldName) return;
      await this._personalityCRUD(
        '/api/personality/rename',
        { old: oldName, new: trimmed },
        `Renamed '${oldName}' → '${trimmed.toLowerCase()}'`
      );
    },

    async duplicatePersonalityPrompt(sourceName) {
      const next = window.prompt(
        `Duplicate '${sourceName}' as:`,
        `${sourceName}_copy`
      );
      if (!next) return;
      const trimmed = next.trim();
      if (!trimmed) return;
      await this._personalityCRUD(
        '/api/personality/duplicate',
        { source: sourceName, name: trimmed },
        `Duplicated '${sourceName}' → '${trimmed.toLowerCase()}'`
      );
    },

    async deletePersonalityConfirm(name) {
      if (this.personalityNames().length <= 1) {
        this.statusText = 'Cannot delete the last remaining personality.';
        return;
      }
      const proceed = window.confirm(
        `Delete personality '${name}'? This removes its scene/bank assignments. Cannot be undone in the draft (use Discard to revert from disk).`
      );
      if (!proceed) return;
      await this._personalityCRUD(
        '/api/personality/delete',
        { name },
        `Deleted personality '${name}'`
      );
    },

    async setDryRun() {
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch: { dry_run: Boolean(this.draftDryRun) } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Failed to update dry_run';
          return;
        }
        this.statusText = `dry_run=${this.draftDryRun ? 'true' : 'false'}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Dry run update failed: ${err.message}`;
      }
    },

    currentSceneConfig() {
      if (this.openNote === null || this.openNote === undefined) return null;
      const sceneName = this.drawerSceneDetails().sceneName;
      return sceneName ? this.config?.scenes?.[sceneName] || null : null;
    },

    drawerSceneDetails() {
      if (this.openNote === null || this.openNote === undefined) {
        return { mapped: false, sceneName: '', role: '', personality: this.drawerPersonalityName() };
      }
      return this.sceneDetailsByNote(this.openNote, this.drawerPersonalityName());
    },

    async queueScenePatch(sceneName, scenePatch) {
      if (!sceneName) return;
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch: { scenes: { [sceneName]: scenePatch } } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Scene update failed';
          return;
        }
        this.statusText = `Updated ${sceneName}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Scene update failed: ${err.message}`;
      }
    },

    midiNoteName(note) {
      const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
      const n = Number(note);
      if (!Number.isFinite(n)) return '';
      return `${names[((n % 12) + 12) % 12]}${Math.floor(n / 12) - 1}`;
    },

    sceneMidi(sceneName) {
      const scene = this.config?.scenes?.[sceneName] || {};
      return scene.midi || {};
    },

    sceneBehaviorText(sceneName) {
      const midi = this.sceneMidi(sceneName);
      const behavior = String(midi.behavior || 'pulse');
      if (behavior === 'hold_beats') return `hold ${Number(midi.hold_beats || 0)} beats`;
      if (behavior === 'hold_ms') return `hold ${Number(midi.hold_ms || midi.duration_ms || 0)}ms`;
      return `${behavior} ${Number(midi.duration_ms || 80)}ms`;
    },

    tileBehaviorText(note) {
      const meta = this.sceneDetailsByNote(note);
      if (!meta.mapped) return '';
      if (meta.behavior === 'hold_beats') return `hold ${Number(meta.hold_beats || 0)} beats`;
      return meta.behavior || 'pulse';
    },

    primarySceneForRole(role) {
      const [sceneField] = this._roleSceneFields(role);
      return sceneField ? this.drawerPersonalityData()?.[sceneField] || '' : '';
    },

    roleBankScenes(role) {
      const [_sceneField, bankField] = this._roleSceneFields(role);
      const pdata = this.drawerPersonalityData() || {};
      const primary = this.primarySceneForRole(role);
      const bank = Array.isArray(pdata[bankField]) ? pdata[bankField] : [];
      return [primary, ...bank].filter((name, idx, arr) => name && arr.indexOf(name) === idx);
    },

    async makeScenePrimary(role, sceneName) {
      const [sceneField, bankField] = this._roleSceneFields(role);
      if (!sceneField || !bankField || !sceneName) return;
      const personality = this.drawerPersonalityName();
      const bank = this.roleBankScenes(role);
      const reordered = [sceneName, ...bank.filter((name) => name !== sceneName)];
      const patch = {
        personalities: {
          [personality]: {
            [sceneField]: sceneName,
            [bankField]: reordered,
          },
        },
      };
      if (role === 'groove') {
        patch.personalities[personality].default_scene = sceneName;
      }
      await this.applyPatch(patch, `Primary ${role} mapping set to ${sceneName}`);
    },

    async removeSceneFromBank(role, sceneName) {
      const [sceneField, bankField] = this._roleSceneFields(role);
      if (!sceneField || !bankField || !sceneName) return;
      const proceed = window.confirm(`Remove ${sceneName} from ${role} bank?`);
      if (!proceed) return;
      const personality = this.drawerPersonalityName();
      const nextBank = this.roleBankScenes(role).filter((name) => name !== sceneName);
      const nextPrimary = this.primarySceneForRole(role) === sceneName ? (nextBank[0] || '') : this.primarySceneForRole(role);
      const patch = {
        personalities: {
          [personality]: {
            [sceneField]: nextPrimary,
            [bankField]: nextBank,
          },
        },
      };
      if (role === 'groove') {
        patch.personalities[personality].default_scene = nextPrimary;
      }
      await this.applyPatch(patch, `Removed ${sceneName} from ${role} bank`);
    },

    async addSceneToCurrentBankPrompt() {
      const noteRaw = window.prompt('Pick an unmapped MIDI note to add:', '');
      if (noteRaw === null) return;
      const note = Number(noteRaw);
      if (!Number.isFinite(note) || note < 0 || note > 127) {
        this.statusText = 'MIDI note must be 0-127.';
        return;
      }
      const meta = this.sceneDetailsByNote(note, this.drawerPersonalityName());
      if (meta.mapped) {
        this.statusText = `Note ${note} is already mapped — pick an unmapped note.`;
        return;
      }
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mapping: {
              personality: this.drawerPersonalityName(),
              role: this.drawer.role || this.currentBank()?.default_role || 'groove',
              note,
              channel: Number(this.currentBank()?.channel || 1),
              velocity: Number(this.drawer.velocity || 127),
              behavior: this.drawer.behavior || 'pulse',
              hold_beats: Number(this.drawer.hold_beats || 4),
              duration_ms: Number(this.drawer.duration_ms || 80),
              cooldown_beats: Number(this.drawer.cooldown_beats || 8),
              safety_class: this.drawer.safety_class || this.currentBank()?.default_safety || 'movement_low',
              immediate: Boolean(this.drawer.immediate),
              label: '',
              add_to_bank: true,
              replace_primary: false,
            },
          }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Failed to add bank scene';
          return;
        }
        this.statusText = `Added ${data.scene_name || `note ${note}`} to ${this.drawer.role} bank`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Failed to add bank scene: ${err.message}`;
      }
    },

    async applyPatch(patch, successMsg) {
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Draft update failed';
          return false;
        }
        this.statusText = successMsg;
        await this.refreshConfig();
        return true;
      } catch (err) {
        this.statusText = `Draft update failed: ${err.message}`;
        return false;
      }
    },

    async patchBanks(banks, successMsg = 'Banks updated') {
      return this.applyPatch({ _pad_meta: { banks } }, successMsg);
    },

    async moveOpenNoteToBank(targetBankId) {
      if (!targetBankId || this.openNote === null || this.openNote === undefined) return;
      const note = Number(this.openNote);
      const sourceBank = this.currentBank();
      const targetBank = this.bankById(targetBankId);
      if (!sourceBank || !targetBank) return;
      const sourceChannel = Number(sourceBank.channel || 1);
      const targetChannel = Number(targetBank.channel || 1);
      if (sourceChannel !== targetChannel) {
        const proceed = window.confirm(
          `Move note ${note} from Ch${sourceChannel} to ${targetBank.name} Ch${targetChannel}? The scene MIDI channel will be updated.`
        );
        if (!proceed) return;
      }
      const banks = this.banks().map((bank) => {
        const notes = Array.isArray(bank.notes) ? bank.notes.filter((n) => Number(n) !== note) : [];
        if (bank.id === targetBankId && !notes.includes(note)) {
          notes.push(note);
          notes.sort((a, b) => Number(a) - Number(b));
        }
        return { ...bank, notes };
      });
      const meta = this.sceneDetailsByNote(note);
      const patch = { _pad_meta: { banks } };
      if (meta.mapped && meta.sceneName) {
        patch.scenes = {
          [meta.sceneName]: {
            midi: {
              note,
              channel: targetChannel,
            },
          },
        };
      }
      const ok = await this.applyPatch(patch, `Moved note ${note} to ${targetBank.name}`);
      if (ok) this.activeBankId = targetBankId;
    },

    rawSceneJson(note) {
      const meta = this.sceneDetailsByNote(note);
      if (!meta.sceneName) return '{}';
      return JSON.stringify(this.config?.scenes?.[meta.sceneName] || {}, null, 2);
    },

    syncTimingDraft() {
      const pdata = this.personalityData();
      this.timingDraft = {
        phrase_interval_beats: Number(pdata?.phrase_interval_beats ?? 32),
        minimum_scene_hold_beats: Number(pdata?.minimum_scene_hold_beats ?? 8),
        buildup_lookahead_beats: Number(pdata?.buildup_lookahead_beats ?? 32),
      };
    },

    canSaveTimingDraft() {
      const phrase = Number(this.timingDraft.phrase_interval_beats);
      const hold = Number(this.timingDraft.minimum_scene_hold_beats);
      const lookahead = Number(this.timingDraft.buildup_lookahead_beats);
      return Number.isFinite(phrase) && phrase >= 1
        && Number.isFinite(hold) && hold >= 0
        && Number.isFinite(lookahead) && lookahead >= 1;
    },

    async saveTimingDraft() {
      if (!this.canSaveTimingDraft()) {
        this.statusText = 'Timing values are invalid.';
        return;
      }
      const personality = this.activePersonality();
      const patch = {
        personalities: {
          [personality]: {
            phrase_interval_beats: Number(this.timingDraft.phrase_interval_beats),
            minimum_scene_hold_beats: Number(this.timingDraft.minimum_scene_hold_beats),
            buildup_lookahead_beats: Number(this.timingDraft.buildup_lookahead_beats),
          },
        },
      };
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Failed to update timing';
          return;
        }
        this.statusText = `Updated timing for ${personality}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Timing save failed: ${err.message}`;
      }
    },

    async commitDraft() {
      try {
        const response = await fetch('/api/commit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const data = await response.json();
        this.statusText = data.ok ? 'Committed draft' : `Commit failed: ${(data.errors || []).join('; ')}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Commit failed: ${err.message}`;
      }
    },

    async discardDraft() {
      try {
        const response = await fetch('/api/discard', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Discard failed';
          return;
        }
        await this.refreshConfig();
        this.statusText = 'Draft discarded and reloaded from disk';
      } catch (err) {
        this.statusText = `Discard failed: ${err.message}`;
      }
    },

    async verifyDraft() {
      try {
        this.verifyByNote = {};
        const validateResponse = await fetch('/api/validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const validateData = await validateResponse.json();
        const errors = Array.isArray(validateData.errors) ? validateData.errors : [];
        const warnings = Array.isArray(validateData.warnings) ? validateData.warnings : [];
        this.validateResults = { errors, warnings };

        const verifyResponse = await fetch('/api/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const data = await verifyResponse.json();
        const checks = Array.isArray(data.checks) ? data.checks : [];
        this.verifyResults = { checks };
        const verifyByNote = {};
        checks.forEach((row) => {
          if (row && row.ok === false && row.channel !== undefined && row.note !== undefined) {
            verifyByNote[`${Number(row.channel)}:${Number(row.note)}`] = {
              ok: false,
              detail: String(row.detail || row.name || 'verify failed'),
            };
          }
        });
        this.verifyByNote = verifyByNote;
        this.showVerifyPanel = true;
        const failed = checks.filter((row) => !row.ok).length;
        this.statusText = `Diagnostics: ${errors.length} error(s), ${warnings.length} warning(s), ${failed}/${checks.length} verify failures`;
      } catch (err) {
        this.statusText = `Diagnostics failed: ${err.message}`;
      }
    },

    async sendTest(channel, note, overrides = {}) {
      this.flashFiringNote(note, 700);
      this.flashNoteElement(note, 700);
      try {
        const payload = {
          ...this.test,
          ...overrides,
          channel,
          note,
        };
        const response = await fetch('/api/test_note', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok || data?.ok === false) {
          this.statusText = data?.error || 'Test note failed';
          return;
        }
        this.statusText = `Fired note ${Number(note)} @ Ch${Number(channel)}`;
      } catch (err) {
        this.statusText = `Test note failed: ${err.message}`;
      }
    },

    flashFiringNote(note, durationMs = 700) {
      this.firingNote = Number(note);
      if (this.firingTimer) {
        clearTimeout(this.firingTimer);
      }
      this.firingTimer = setTimeout(() => {
        this.firingNote = null;
        this.firingTimer = null;
      }, Math.max(120, Number(durationMs) || 700));
    },

    flashNoteElement(note, durationMs = 700) {
      if (typeof document === 'undefined') return;
      const buttons = document.querySelectorAll('.note-grid .note-btn');
      if (!buttons.length) return;
      const target = Array.from(buttons).find((btn) => {
        const numEl = btn.querySelector('.note-num');
        return numEl && Number(numEl.textContent) === Number(note);
      });
      if (!target) return;
      target.classList.remove('firing');
      // Force reflow so animation restarts on rapid taps
      void target.offsetWidth;
      target.classList.add('firing');
      setTimeout(() => {
        target.classList.remove('firing');
      }, Math.max(120, Number(durationMs) || 700));
    },

    handleNoteMouseUp(note, event) {
      if (event && event.button !== 0) {
        return;
      }
      if (this.draggedNote !== null) {
        return;
      }
      if (this.suppressClickNote === Number(note)) {
        this.suppressClickNote = null;
        return;
      }
      const meta = this.sceneDetailsByNote(note);
      const channel = Number(meta.channel || this.currentBank()?.channel || 1);
      this.sendTest(channel, note);
    },

    handleNoteKeyboardFire(note) {
      const meta = this.sceneDetailsByNote(note);
      const channel = Number(meta.channel || this.currentBank()?.channel || 1);
      this.sendTest(channel, note);
    },

    startTouchLongPress(note) {
      this.cancelTouchLongPress();
      this.touchLongPressed = false;
      this.pressProgress = { note: Number(note), startedAt: Date.now() };
      this.touchLongPressTimer = setTimeout(() => {
        this.openDrawerPlaceholder(note);
        this.suppressClickNote = Number(note);
        this.touchLongPressed = true;
        this.touchLongPressTimer = null;
        this.pressProgress = { note: null, startedAt: 0 };
      }, 500);
    },

    endTouchLongPress(note) {
      if (this.touchLongPressTimer) {
        clearTimeout(this.touchLongPressTimer);
        this.touchLongPressTimer = null;
        const meta = this.sceneDetailsByNote(note);
        const channel = Number(meta.channel || this.currentBank()?.channel || 1);
        this.sendTest(channel, note);
      } else if (this.touchLongPressed) {
        this.touchLongPressed = false;
      }
      this.pressProgress = { note: null, startedAt: 0 };
    },

    cancelTouchLongPress() {
      if (this.touchLongPressTimer) {
        clearTimeout(this.touchLongPressTimer);
        this.touchLongPressTimer = null;
      }
      this.touchLongPressed = false;
      this.pressProgress = { note: null, startedAt: 0 };
    },

    openDrawerPlaceholder(note) {
      const meta = this.sceneDetailsByNote(note);
      this.openNote = note;
      this.drawer.personality = meta.personality || this.activePersonality();
      this.drawer.role = meta.role || this.currentBank()?.default_role || 'groove';
      this.drawer.source_behavior = meta.behavior || this.currentBank()?.default_behavior || 'pulse';
      this.drawer.behavior = ['pulse', 'hold_beats'].includes(this.drawer.source_behavior)
        ? this.drawer.source_behavior
        : 'pulse';
      this.drawer.behaviorTouched = false;
      this.drawer.velocity = Number(meta.velocity ?? 127);
      this.drawer.hold_beats = Number(meta.hold_beats ?? (this.currentBank()?.default_hold_beats || 4));
      this.drawer.duration_ms = Number(meta.duration_ms ?? (this.currentBank()?.default_duration_ms || 80));
      this.drawer.cooldown_beats = Number(meta.cooldown_beats ?? (this.currentBank()?.default_cooldown_beats || 8));
      this.drawer.safety_class = meta.safetyClass || this.currentBank()?.default_safety || 'movement_low';
      this.drawer.immediate = Boolean(meta.immediate);
      this.drawer.label = meta.label || '';
      this.drawer.system = Boolean(meta.system);
      this.statusText = `Editing note ${note}`;
    },

    closeDrawer() {
      this.openNote = null;
    },

    drawerIsMapped() {
      if (this.openNote === null || this.openNote === undefined) return false;
      return this.drawerSceneDetails().mapped;
    },

    drawerRoleChanged() {
      const meta = this.drawerSceneDetails();
      return Boolean(meta.mapped && this.drawer.role && meta.role && this.drawer.role !== meta.role);
    },

    _roleSceneFields(role) {
      const map = {
        groove: ['phrase_scene', 'phrase_bank'],
        buildup: ['buildup_scene', 'buildup_bank'],
        drop: ['drop_scene', 'drop_bank'],
        post_drop: ['post_drop_scene', 'post_drop_bank'],
        breakdown: ['breakdown_scene', 'breakdown_bank'],
      };
      return map[role] || ['', ''];
    },

    async setDrawerPrimary() {
      if (this.openNote === null || this.openNote === undefined) return;
      const meta = this.drawerSceneDetails();
      if (!meta.mapped || !meta.sceneName || !meta.role) return;
      if (this.drawerRoleChanged()) {
        this.statusText = 'Apply role change before setting primary.';
        return;
      }
      const personality = this.drawerPersonalityName();
      const [sceneField, bankField] = this._roleSceneFields(meta.role);
      if (!sceneField || !bankField) return;
      const pdata = this.drawerPersonalityData() || {};
      const existingBank = Array.isArray(pdata[bankField]) ? [...pdata[bankField]] : [];
      const reorderedBank = [meta.sceneName, ...existingBank.filter((name) => name !== meta.sceneName)];
      const patch = {
        personalities: {
          [personality]: {
            [sceneField]: meta.sceneName,
            [bankField]: reorderedBank,
          },
        },
      };
      if (meta.role === 'groove') {
        patch.personalities[personality].default_scene = meta.sceneName;
      }
      const response = await fetch('/api/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patch }),
      });
      const data = await response.json();
      if (!data.ok) {
        this.statusText = data.error || 'Failed to set primary mapping';
        return;
      }
      this.statusText = `Primary ${meta.role} mapping set to ${meta.sceneName}`;
      await this.refreshConfig();
    },

    async removeDrawerMapping() {
      if (this.openNote === null || this.openNote === undefined) return;
      const meta = this.drawerSceneDetails();
      if (!meta.mapped || !meta.sceneName || !meta.role) return;
      const proceed = window.confirm(`Remove mapping ${meta.sceneName}?`);
      if (!proceed) return;
      const personality = this.drawerPersonalityName();
      const [sceneField, bankField] = this._roleSceneFields(meta.role);
      if (!sceneField || !bankField) return;
      const pdata = this.drawerPersonalityData() || {};
      const existingBank = Array.isArray(pdata[bankField]) ? [...pdata[bankField]] : [];
      const newBank = existingBank.filter((name) => name !== meta.sceneName);
      const fallbackPrimary = newBank[0] || '';
      const personalityPatch = {
        [bankField]: newBank,
        [sceneField]: fallbackPrimary,
      };
      if (meta.role === 'groove') {
        personalityPatch.default_scene = fallbackPrimary;
      }
      if (meta.role === 'drop') {
        const dropStyle = String(pdata.drop_style || 'drop_mode');
        if (dropStyle === 'drop_mode') {
          personalityPatch.post_drop_scene = fallbackPrimary;
          personalityPatch.post_drop_bank = fallbackPrimary ? [fallbackPrimary] : [];
        }
      }
      const patch = {
        scenes: {
          [meta.sceneName]: null,
        },
        personalities: {
          [personality]: personalityPatch,
        },
      };
      const response = await fetch('/api/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patch }),
      });
      const data = await response.json();
      if (!data.ok) {
        this.statusText = data.error || 'Failed to remove mapping';
        return;
      }
      this.statusText = `Removed mapping ${meta.sceneName}`;
      this.openNote = null;
      await this.refreshConfig();
    },

    drawerValidationErrors() {
      const errors = {};
      const velocity = Number(this.drawer.velocity);
      const holdBeats = Number(this.drawer.hold_beats);
      const cooldown = Number(this.drawer.cooldown_beats);
      if (!Number.isFinite(velocity) || velocity < 0 || velocity > 127) {
        errors.velocity = 'Velocity must be between 0 and 127.';
      }
      if (this.drawer.behavior === 'hold_beats' && (!Number.isFinite(holdBeats) || holdBeats <= 0)) {
        errors.hold_beats = 'Hold beats must be > 0 for hold_beats.';
      }
      if (!Number.isFinite(cooldown) || cooldown < 0) {
        errors.cooldown_beats = 'Cooldown must be >= 0.';
      }
      return errors;
    },

    fieldError(field) {
      return this.drawerValidationErrors()[field] || '';
    },

    canApplyDrawer() {
      return Object.keys(this.drawerValidationErrors()).length === 0;
    },

    queueDraftSave() {
      if (!this.openNote && this.openNote !== 0) return;
      if (!this.canApplyDrawer()) {
        if (this.draftTimer) {
          clearTimeout(this.draftTimer);
          this.draftTimer = null;
        }
        return;
      }
      if (this.draftTimer) {
        clearTimeout(this.draftTimer);
      }
      this.draftTimer = setTimeout(() => {
        this.persistDrawer();
      }, 500);
    },

    async persistDrawer() {
      if (!this.openNote && this.openNote !== 0) return;
      if (this.drawer.system) return;
      if (!this.canApplyDrawer()) {
        this.statusText = 'Fix drawer validation errors before applying.';
        return;
      }
      try {
        const effectiveBehavior = this.drawer.behaviorTouched
          ? this.drawer.behavior
          : this.drawer.source_behavior;
        const payload = {
          mapping: {
            personality: this.drawer.personality,
            role: this.drawer.role,
            note: Number(this.openNote),
            channel: Number(this.currentBank()?.channel || 1),
            velocity: Number(this.drawer.velocity),
            behavior: effectiveBehavior,
            hold_beats: Number(this.drawer.hold_beats),
            duration_ms: Number(this.drawer.duration_ms),
            cooldown_beats: Number(this.drawer.cooldown_beats),
            safety_class: this.drawer.safety_class,
            immediate: Boolean(this.drawer.immediate),
            label: this.drawer.label,
            add_to_bank: false,
            replace_primary: true,
          },
        }
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (data.ok) {
          this.statusText = `Draft updated${data.scene_name ? ` (${data.scene_name})` : ''}`;
          await this.refreshConfig();
        } else {
          this.statusText = data.error || 'Failed to update draft';
        }
      } catch (err) {
        this.statusText = `Drawer apply failed: ${err.message}`;
      }
    },

    dragStart(note, event) {
      const meta = this.sceneDetailsByNote(note);
      if (!meta.mapped || meta.system) {
        event.preventDefault();
        return;
      }
      this.draggedNote = note;
      this.dropTargetNote = null;
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', String(note));
      }
    },

    dragEnter(note, event) {
      if (this.draggedNote === null) return;
      event.preventDefault();
      this.dropTargetNote = note;
    },

    dragOver(note, event) {
      if (this.draggedNote === null) return;
      event.preventDefault();
      this.dropTargetNote = note;
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'move';
      }
    },

    dragLeave(note) {
      if (this.dropTargetNote === note) {
        this.dropTargetNote = null;
      }
    },

    dragEnd() {
      this.draggedNote = null;
      this.dropTargetNote = null;
    },

    isDropTarget(note) {
      return this.draggedNote !== null && this.dropTargetNote === note;
    },

    dropOn(note, event) {
      if (this.draggedNote === null) return;
      event.preventDefault();
      const sourceNote = this.draggedNote;
      this.dragEnd();
      if (sourceNote === note) {
        return;
      }
      const targetMeta = this.sceneDetailsByNote(note);
      if (targetMeta.system) {
        this.statusText = 'Cannot overwrite blackout system mappings.';
        return;
      }
      if (targetMeta.mapped) {
        this.overwriteDialog = {
          open: true,
          sourceNote,
          targetNote: note,
          pending: { sourceNote, targetNote: note },
        };
        return;
      }
      this.applyDragReassign(sourceNote, note, false);
    },

    cancelOverwrite() {
      this.overwriteDialog = {
        open: false,
        sourceNote: null,
        targetNote: null,
        pending: null,
      };
    },

    confirmOverwrite() {
      const pending = this.overwriteDialog.pending;
      this.cancelOverwrite();
      if (!pending) return;
      this.applyDragReassign(pending.sourceNote, pending.targetNote, true);
    },

    async applyDragReassign(sourceNote, targetNote, allowSwap) {
      const sourceMeta = this.sceneDetailsByNote(sourceNote);
      if (!sourceMeta.mapped || !sourceMeta.sceneName) {
        this.statusText = 'Cannot drag an unmapped note.';
        return;
      }
      const targetMeta = this.sceneDetailsByNote(targetNote);
      if (sourceMeta.system || targetMeta.system) {
        this.statusText = 'Cannot move blackout system mappings.';
        return;
      }
      const sourceBefore = this.cloneMapping(sourceNote);
      const targetBefore = this.cloneMapping(targetNote);
      const targetChannel = Number(this.currentBank()?.channel || 1);
      const patch = {
        scenes: {
          [sourceMeta.sceneName]: {
            midi: {
              note: Number(targetNote),
              channel: targetChannel,
            },
          },
        },
      };
      if (allowSwap && targetMeta.mapped && targetMeta.sceneName) {
        patch.scenes[targetMeta.sceneName] = {
          midi: {
            note: Number(sourceNote),
            channel: Number(sourceMeta.channel || targetChannel),
          },
        };
      }
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Drag/drop update failed';
          return;
        }
        this.armReassignUndo(sourceBefore, targetBefore, sourceNote, targetNote);
        this.statusText = allowSwap
          ? `Swapped note ${sourceNote} with ${targetNote}`
          : `Moved mapping ${sourceNote} → ${targetNote}`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Drag/drop failed: ${err.message}`;
      }
    },

    armReassignUndo(sourceBefore, targetBefore, sourceNote, targetNote) {
      if (this.lastReassignUndo.timer) {
        clearTimeout(this.lastReassignUndo.timer);
      }
      const scenes = {
        ...this.patchForSnapshot(sourceBefore),
        ...this.patchForSnapshot(targetBefore),
      };
      this.lastReassignUndo = {
        visible: true,
        message: `Moved ${sourceNote} -> ${targetNote}`,
        patch: { scenes },
        timer: setTimeout(() => {
          this.lastReassignUndo.visible = false;
          this.lastReassignUndo.patch = null;
          this.lastReassignUndo.timer = null;
        }, 10000),
      };
    },

    async undoLastReassign() {
      const patch = this.lastReassignUndo.patch;
      if (!patch) return;
      if (this.lastReassignUndo.timer) {
        clearTimeout(this.lastReassignUndo.timer);
      }
      this.lastReassignUndo.visible = false;
      this.lastReassignUndo.patch = null;
      this.lastReassignUndo.timer = null;
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Undo failed';
          return;
        }
        this.statusText = 'Reassign undone';
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Undo failed: ${err.message}`;
      }
    },

    openSettingsPanel() {
      this.settingsOpen = true;
      this.syncBlackoutForm();
    },

    closeSettingsPanel() {
      this.settingsOpen = false;
    },

    syncBlackoutForm() {
      const manual = this.config?.manual_commands || {};
      const seed = (existing, fallback) => ({
        channel: Number(existing?.channel ?? fallback.channel),
        note: Number(existing?.note ?? fallback.note),
        velocity: Number(existing?.velocity ?? fallback.velocity),
        duration_ms: Number(existing?.duration_ms ?? fallback.duration_ms),
      });
      this.blackoutForm = {
        on: seed(manual.blackout_on, { channel: 1, note: 0, velocity: 127, duration_ms: 80 }),
        off: seed(manual.blackout_off, { channel: 1, note: 1, velocity: 127, duration_ms: 80 }),
      };
    },

    blackoutConfigured(which) {
      const manual = this.config?.manual_commands || {};
      const key = which === 'on' ? 'blackout_on' : 'blackout_off';
      return !!manual[key];
    },

    async saveBlackout(which) {
      const slot = which === 'on' ? 'blackout_on' : 'blackout_off';
      const form = this.blackoutForm[which] || {};
      const isOn = which === 'on';
      const message = {
        kind: isOn ? 'note_on' : 'note_off',
        behavior: isOn ? 'note_on' : 'note_off',
        channel: Math.max(1, Math.min(16, Number(form.channel) || 1)),
        note: Math.max(0, Math.min(127, Number(form.note) || 0)),
        velocity: Math.max(0, Math.min(127, Number(form.velocity) || 127)),
      };
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch: { manual_commands: { [slot]: message } } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || `Failed to save ${slot}`;
          return;
        }
        this.statusText = `${slot} saved`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `${slot} save failed: ${err.message}`;
      }
    },

    async saveBank(index, field, value) {
      const banks = this.banks().map((bank) => ({ ...bank }));
      if (!banks[index]) return;
      const trimmed = field === 'name' ? String(value || '').trim() : Number(value);
      if (field === 'name' && !trimmed) {
        this.statusText = 'Bank name cannot be empty.';
        return;
      }
      if (field === 'channel' && (!Number.isFinite(trimmed) || trimmed < 1 || trimmed > 16)) {
        this.statusText = 'Channel must be 1-16.';
        return;
      }
      banks[index] = { ...banks[index], [field]: trimmed };
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch: { _pad_meta: { banks } } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Bank update failed';
          return;
        }
        this.statusText = `Bank ${index + 1} ${field} updated`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Bank update failed: ${err.message}`;
      }
    },

    async resetBanksToDefault() {
      const proceed = window.confirm('Reset all banks to default 4 × 32 layout? Custom names and channels will be lost.');
      if (!proceed) return;
      try {
        const response = await fetch('/api/banks/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || 'Reset banks failed';
          return;
        }
        this.statusText = 'Banks reset to default (4 × 32)';
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `Reset banks failed: ${err.message}`;
      }
    },

    async clearBlackout(which) {
      const slot = which === 'on' ? 'blackout_on' : 'blackout_off';
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch: { manual_commands: { [slot]: null } } }),
        });
        const data = await response.json();
        if (!data.ok) {
          this.statusText = data.error || `Failed to clear ${slot}`;
          return;
        }
        this.statusText = `${slot} cleared`;
        await this.refreshConfig();
      } catch (err) {
        this.statusText = `${slot} clear failed: ${err.message}`;
      }
    },

    openHistoryPanel() {
      this.historyOpen = true;
      this.loadHistory();
    },

    closeHistoryPanel() {
      this.historyOpen = false;
      this.historySelected = null;
      this.historyDiff = '';
    },

    formatHistoryTime(mtime) {
      if (!mtime) return '';
      return new Date(Number(mtime) * 1000).toLocaleString();
    },

    formatHistorySize(size) {
      const bytes = Number(size || 0);
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
    },

    async loadHistory() {
      this.historyLoading = true;
      try {
        const response = await fetch('/api/history');
        const data = await response.json();
        this.historyItems = Array.isArray(data.items) ? data.items : [];
        if (this.historySelected) {
          const match = this.historyItems.find((item) => item.name === this.historySelected.name);
          this.historySelected = match || null;
        }
      } catch (err) {
        this.statusText = `History load failed: ${err.message}`;
      } finally {
        this.historyLoading = false;
      }
    },

    async selectHistoryItem(name) {
      this.historySelected = this.historyItems.find((item) => item.name === name) || { name };
      try {
        const response = await fetch(`/api/history/${name}/diff`);
        const data = await response.json();
        if (response.ok && typeof data.diff === 'string') {
          this.historyDiff = data.diff;
        } else {
          this.historyDiff = data.error || 'Unable to load diff.';
        }
      } catch (err) {
        this.historyDiff = `Failed to load diff: ${err.message}`;
      }
    },

    async restoreSelectedHistory() {
      if (!this.historySelected) return;
      const proceed = window.confirm(`Restore ${this.historySelected.name}?`);
      if (!proceed) return;
      try {
        const response = await fetch(`/api/history/${this.historySelected.name}/restore`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const data = await response.json();
        if (!response.ok) {
          this.statusText = data.error || 'Restore failed';
          return;
        }
        this.statusText = `Restored ${this.historySelected.name} to draft`;
        await this.refreshConfig();
        await this.loadHistory();
      } catch (err) {
        this.statusText = `Restore failed: ${err.message}`;
      }
    },
  };
};

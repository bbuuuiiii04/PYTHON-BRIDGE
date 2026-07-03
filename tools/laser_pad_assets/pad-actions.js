window.LaserPad = window.LaserPad || {};

(function laserPadModule(ns) {
  const ROLE_FIELDS = ns.ROLE_FIELDS;
  const BANK_ROLES = ns.BANK_ROLES;
  const PERSONALITY_COLOR_PALETTE = ns.PERSONALITY_COLOR_PALETTE;
  const hardDuplicateMap = ns.hardDuplicateMap;

  ns.actions = {


    markSaving() {
      this.saveState = { ...this.saveState, kind: 'saving', lastError: '', applied: false };
    },



    markSaved() {
      const now = new Date();
      this.saveState = {
        kind: 'saved',
        timestamp: now.toLocaleTimeString(),
        lastError: '',
      };
    },



    markSaveError(message) {
      this.saveState = {
        ...this.saveState,
        kind: 'error',
        lastError: String(message || 'Save failed'),
      };
    },



    async draftPost(body, { successMsg, refresh = true } = {}) {
      this.markSaving();
      try {
        const response = await fetch('/api/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await response.json();
        if (!data.ok) {
          const msg = data.error || 'Save failed';
          this.statusText = msg;
          this.markSaveError(msg);
          return { ok: false, data };
        }
        if (successMsg) this.statusText = successMsg;
        if (refresh) await this.refreshConfig();
        this.markSaved();
        return { ok: true, data };
      } catch (err) {
        const msg = `Save failed: ${err.message}`;
        this.statusText = msg;
        this.markSaveError(msg);
        return { ok: false, error: err };
      }
    },


    queuedDraftPost(key, body, { successMsg, refresh = true } = {}) {
      const queueKey = String(key || 'default');
      if (!(this._draftQueues instanceof Map)) {
        this._draftQueues = new Map();
      }
      const previous = this._draftQueues.get(queueKey);
      if (previous?.timer) {
        clearTimeout(previous.timer);
      }
      if (previous?.controller) {
        previous.controller.abort();
      }
      if (typeof previous?.resolve === 'function') {
        previous.resolve({ ok: false, aborted: true });
      }

      const controller = new AbortController();
      const entry = {
        timer: null,
        timeoutTimer: null,
        controller,
        timedOut: false,
        resolve: null,
      };
      this._draftQueues.set(queueKey, entry);
      this.markSaving();

      return new Promise((resolve) => {
        entry.resolve = resolve;
        entry.timer = setTimeout(async () => {
          entry.timer = null;
          entry.timeoutTimer = setTimeout(() => {
            entry.timedOut = true;
            controller.abort();
          }, 10000);
          try {
            const response = await fetch('/api/draft', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body),
              signal: controller.signal,
            });
            if (entry.timeoutTimer) clearTimeout(entry.timeoutTimer);
            const data = await response.json();
            if (!data.ok) {
              const msg = data.error || 'Save failed';
              this.statusText = msg;
              this.markSaveError(msg);
              resolve({ ok: false, data });
              return;
            }
            if (successMsg) this.statusText = successMsg;
            if (refresh) await this.refreshConfig();
            this.markSaved();
            resolve({ ok: true, data });
          } catch (err) {
            if (entry.timeoutTimer) clearTimeout(entry.timeoutTimer);
            if (entry.timedOut) {
              this.statusText = 'Save timed out';
              this.markSaveError('Save timed out');
              resolve({ ok: false, error: err, timeout: true });
              return;
            }
            if (controller.signal.aborted) {
              resolve({ ok: false, aborted: true });
              return;
            }
            const msg = `Save failed: ${err.message}`;
            this.statusText = msg;
            this.markSaveError(msg);
            resolve({ ok: false, error: err });
          } finally {
            if (this._draftQueues.get(queueKey)?.controller === controller) {
              this._draftQueues.delete(queueKey);
            }
          }
        }, 250);
      });
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
        this.syncPersonalityDrafts();
        if (!this.bankById(this.activeBankId)) {
          this.activeBankId = (this.banks()[0] || {}).id || 'bank_1';
        }
        this.duplicateWarning = this.computeDuplicateWarning();
        if (this.test.note === undefined || this.test.note === null) {
          const first = this.currentNotes()[0];
          this.test.note = first || 0;
        }
        const nextHash = this.configHash(this.config);
        this.currentConfigHash = nextHash;
        if (!this.lastCommittedHash) {
          this.lastCommittedHash = nextHash;
        }
        if (this._selectorCache instanceof Map) {
          this._selectorCache.clear();
        }
        // markSaved() is only ever called from real save sites.
      } catch (err) {
        this.statusText = `Couldn't load config: ${err.message}`;
      }
    },



    async openAccessPanel() {
      this.accessOpen = true;
      this.accessInfo = null;
      this.accessQrSvg = '';
      try {
        const response = await fetch('/api/access');
        const data = await response.json();
        this.accessInfo = data;
        if (data.lan_url) {
          try {
            const qr = qrcode(0, 'M');
            qr.addData(data.lan_url);
            qr.make();
            this.accessQrSvg = qr.createSvgTag({ cellSize: 4, margin: 4 });
          } catch (err) {
            this.accessQrSvg = '';
          }
        }
      } catch (err) {
        this.statusText = `Couldn't check network access: ${err.message}`;
        this.accessInfo = { ok: false, bound_host: '', port: 0, loopback_only: true, lan_url: null };
      }
    },



    closeAccessPanel() {
      this.accessOpen = false;
    },



    syncTestUi() {
      const ui = this.config?._pad_meta?.ui || {};
      this.test.bpm = Number(ui.bpm_for_test_fire ?? this.test.bpm ?? 128);
      this.test.velocity = Number(ui.last_test_velocity ?? this.test.velocity ?? 127);
      this.test.hold_beats = Number(ui.last_test_hold_beats ?? this.test.hold_beats ?? 4);
      this.test.channel = Number(ui.last_test_channel ?? this.test.channel ?? 1);
      this.test.note = Number(ui.last_test_note ?? this.test.note ?? 60);
    },



    async setPersonalityColor(name, color) {
      const value = String(color || '').trim();
      if (!/^#[0-9a-fA-F]{6}$/.test(value)) return;
      await this.queuedDraftPost(
        `personality:${name}:color`,
        { patch: { _pad_meta: { personality_colors: { [name]: { color: value.toLowerCase() } } } } },
        { successMsg: '' }
      );
    },



    async setPersonalityInitial(name, initial) {
      const value = String(initial || '').trim().toUpperCase().slice(0, 3);
      if (!value) return;
      await this.queuedDraftPost(
        `personality:${name}:initial`,
        { patch: { _pad_meta: { personality_colors: { [name]: { initial: value } } } } },
        { successMsg: '' }
      );
    },



    async resetPersonalityChip(name) {
      // Backend deep_merge treats null as deletion, so this clears any
      // explicit override and lets the palette auto-assignment take over.
      await this.draftPost(
        { patch: { _pad_meta: { personality_colors: { [name]: null } } } },
        { successMsg: '' }
      );
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
        this.statusText = `Config issues: ${errors.length} error(s), ${warnings.length} warning(s)`;
      } catch (err) {
        this.statusText = `Config check failed: ${err.message}`;
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
      await this.draftPost({ patch }, { successMsg: 'Manual test settings saved', refresh: false });
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
      const values = await this.openPromptModal({
        title: 'Add bank',
        message: 'Pick a name and which MIDI channel it uses.',
        confirmText: 'Create bank',
        fields: [
          { name: 'name', label: 'Bank name', value: `Bank ${this.banks().length + 1}`, placeholder: 'e.g. Bank 5' },
          { name: 'channel', label: 'MIDI channel (1–16)', value: '1', type: 'number', min: 1, max: 16, step: 1 },
        ],
        validate: (input) => {
          const name = String(input.name || '').trim();
          const channel = Number(input.channel);
          if (!name) return 'Bank name is required.';
          if (!Number.isFinite(channel) || channel < 1 || channel > 16) return 'Channel must be 1–16.';
          return '';
        },
      });
      if (!values) return;
      const name = String(values.name || '').trim();
      const channel = Number(values.channel);
      if (!Number.isFinite(channel) || channel < 1 || channel > 16) {
        this.statusText = 'Channel must be 1–16.';
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



    async editBankPrompt(bankId) {
      const index = this.banks().findIndex((bank) => bank.id === bankId);
      if (index < 0) return;
      const bank = this.banks()[index];
      const values = await this.openPromptModal({
        title: 'Rename bank',
        message: 'Update the name and/or MIDI channel.',
        confirmText: 'Save',
        fields: [
          { name: 'name', label: 'Bank name', value: String(bank.name || bank.id || '') },
          { name: 'channel', label: 'MIDI channel (1–16)', value: String(bank.channel || 1), type: 'number', min: 1, max: 16, step: 1 },
        ],
        validate: (input) => {
          const name = String(input.name || '').trim();
          const channel = Number(input.channel);
          if (!name) return 'Bank name is required.';
          if (!Number.isFinite(channel) || channel < 1 || channel > 16) return 'Channel must be 1–16.';
          return '';
        },
      });
      if (!values) return;
      const banks = this.banks().map((b, i) => i === index
        ? { ...b, name: String(values.name || '').trim(), channel: Number(values.channel) }
        : b);
      await this.patchBanks(banks, `Bank ${index + 1} updated`);
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
        this.statusText = `MIDI output refresh failed: ${err.message}`;
      }
    },



    async applyManualPort() {
      const name = String(this.manualPort || '').trim();
      if (!name) return;
      this.selectedPort = name;
      this.manualPort = '';
      const result = await this.setMidiPort();
      if (result?.ok) {
        this.manualPortOpen = false;
      }
    },



    async setMidiPort() {
      if (!this.selectedPort) return;
      return this.draftPost(
        { patch: { midi_output_port: this.selectedPort } },
        { successMsg: `MIDI output: ${this.selectedPort}` }
      );
    },



    async setSmartDropMode(value) {
      const v = String(value || '').trim();
      if (!v) return;
      await this.draftPost(
        { patch: { smart_drop_mode: v } },
        { successMsg: `Drop transition: ${v}` }
      );
    },



    async setLifecycleScene(field, value) {
      const key = String(field || '').trim();
      if (!key) return;
      const v = String(value || '');
      await this.draftPost(
        { patch: { [key]: v } },
        { successMsg: `${this.lifecycleSceneLabel(key)}: ${v || '(none)'}` }
      );
    },



    async setEnabled(enabled) {
      await this.draftPost(
        { patch: { enabled: Boolean(enabled) } },
        { successMsg: `Lasers: ${enabled ? 'on' : 'off'}` }
      );
    },



    async setDefaultPersonality(name) {
      const value = String(name || '').trim();
      if (!value) return;
      await this.draftPost(
        { patch: { default_personality: value } },
        { successMsg: `Default personality: ${value}` }
      );
    },



    async setActivePersonality(name) {
      const value = String(name || '').trim();
      if (!value) return;
      await this.draftPost(
        // /api/draft deep-merges nested dicts; sibling _pad_meta keys are preserved.
        { patch: { _pad_meta: { ui: { last_personality: value } } } },
        { successMsg: `Active personality: ${value}` }
      );
    },



    async savePersonalityPrimaryScene(role, sceneName) {
      const [sceneField, bankField] = this._roleSceneFields(role);
      if (!sceneField) return;
      const personality = this.activePersonality();
      const value = String(sceneName || '').trim();
      const personalityPatch = { [sceneField]: value };
      if (value && bankField) {
        const current = this.personalityBankFor(role);
        personalityPatch[bankField] = current.includes(value) ? current : [...current, value];
      }
      await this.draftPost(
        { patch: { personalities: { [personality]: personalityPatch } } },
        { successMsg: `Saved ${role} primary scene for ${personality}` }
      );
    },



    async saveAliasesDraft() {
      if (!this.canSaveAliasesDraft()) {
        this.statusText = 'Alias values are invalid.';
        return;
      }
      const personality = this.activePersonality();
      await this.draftPost(
        { patch: { personalities: { [personality]: { aliases: this.parseAliasesDraft() } } } },
        { successMsg: `Saved aliases for ${personality}` }
      );
    },



    async saveBpmBandDraft() {
      if (!this.canSaveBpmBandDraft()) {
        this.statusText = 'BPM band values are invalid.';
        return;
      }
      const personality = this.activePersonality();
      await this.draftPost(
        {
          patch: {
            personalities: {
              [personality]: {
                bpm_band_min: Number(this.bpmBandDraft.min),
                bpm_band_max: Number(this.bpmBandDraft.max),
              },
            },
          },
        },
        { successMsg: `Saved BPM band for ${personality}` }
      );
    },



    async resolvePlaylistTest() {
      const params = new URLSearchParams();
      params.set('playlist', String(this.resolverTest.playlist || ''));
      if (String(this.resolverTest.bpm || '').trim()) {
        params.set('bpm', String(this.resolverTest.bpm));
      }
      this.resolverTest.loading = true;
      this.resolverTest.error = '';
      try {
        const response = await fetch('/api/resolve-test?' + params.toString());
        const data = await response.json();
        if (!response.ok || data?.ok === false) {
          this.resolverTest.result = null;
          this.resolverTest.error = data?.error || 'Resolver test failed';
          return;
        }
        this.resolverTest.result = data;
      } catch (err) {
        this.resolverTest.result = null;
        this.resolverTest.error = `Resolver test failed: ${err.message}`;
      } finally {
        this.resolverTest.loading = false;
      }
    },



    async _personalityCRUD(path, body, successMsg) {
      this.markSaving();
      try {
        const response = await fetch(path, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await response.json();
        if (!data.ok) {
          const msg = data.error || 'Personality action failed';
          this.statusText = msg;
          this.markSaveError(msg);
          return false;
        }
        this.statusText = successMsg;
        await this.refreshConfig();
        this.markSaved();
        return true;
      } catch (err) {
        const msg = `Personality action failed: ${err.message}`;
        this.statusText = msg;
        this.markSaveError(msg);
        return false;
      }
    },



    async createPersonalityPrompt() {
      const values = await this.openPromptModal({
        title: 'New personality',
        message: 'Use lowercase letters, digits, and underscores. 1–32 characters.',
        confirmText: 'Create',
        fields: [{ name: 'name', label: 'Name', value: '', placeholder: 'e.g. techno_dark' }],
        validate: (input) => {
          const name = String(input.name || '').trim();
          if (!name) return 'Name is required.';
          if (!/^[a-z0-9_]{1,32}$/.test(name)) return 'Use lowercase letters, digits, underscores only. Max 32 chars.';
          return '';
        },
      });
      if (!values) return;
      const name = String(values.name || '').trim();
      await this._personalityCRUD(
        '/api/personality/create',
        { name },
        `Created personality '${name.trim().toLowerCase()}'`
      );
    },



    async renamePersonalityPrompt(oldName) {
      const values = await this.openPromptModal({
        title: `Rename personality '${oldName}'`,
        message: 'Type a new name. Use lowercase letters, digits, and underscores. 1–32 characters.',
        confirmText: 'Rename',
        fields: [{ name: 'name', label: 'Name', value: String(oldName || '') }],
        validate: (input) => {
          const next = String(input.name || '').trim();
          if (!next) return 'Name is required.';
          if (!/^[a-z0-9_]{1,32}$/.test(next)) return 'Use lowercase letters, digits, underscores only. Max 32 chars.';
          return '';
        },
      });
      if (!values) return;
      const trimmed = String(values.name || '').trim();
      if (!trimmed || trimmed.toLowerCase() === oldName) return;
      await this._personalityCRUD(
        '/api/personality/rename',
        { old: oldName, new: trimmed },
        `Renamed '${oldName}' → '${trimmed.toLowerCase()}'`
      );
    },



    async duplicatePersonalityPrompt(sourceName) {
      const values = await this.openPromptModal({
        title: `Duplicate personality '${sourceName}' as…`,
        message: 'Pick a new name for the copy. Use lowercase letters, digits, and underscores. 1–32 characters.',
        confirmText: 'Duplicate',
        fields: [{ name: 'name', label: 'Name', value: `${sourceName}_copy` }],
        validate: (input) => {
          const next = String(input.name || '').trim();
          if (!next) return 'Name is required.';
          if (!/^[a-z0-9_]{1,32}$/.test(next)) return 'Use lowercase letters, digits, underscores only. Max 32 chars.';
          return '';
        },
      });
      if (!values) return;
      const trimmed = String(values.name || '').trim();
      if (!trimmed) return;
      await this._personalityCRUD(
        '/api/personality/duplicate',
        { source: sourceName, name: trimmed },
        `Duplicated '${sourceName}' → '${trimmed.toLowerCase()}'`
      );
    },



    async deletePersonalityConfirm(name) {
      if (this.personalityNames().length <= 1) {
        this.statusText = "Can't delete the last remaining personality.";
        return;
      }
      const proceed = await this.openConfirmModal({
        title: `Delete personality '${name}'?`,
        message: 'This removes its scenes and bank assignments. You can still recover by discarding unsaved changes.',
        confirmText: 'Delete',
        danger: true,
      });
      if (!proceed) return;
      await this._personalityCRUD(
        '/api/personality/delete',
        { name },
        `Deleted personality '${name}'`
      );
    },



    async setDryRun() {
      await this.draftPost(
        { patch: { dry_run: Boolean(this.draftDryRun) } },
        { successMsg: `Test mode: ${this.draftDryRun ? 'on' : 'off'}` }
      );
    },



    async queueScenePatch(sceneName, scenePatch) {
      if (!sceneName) return;
      await this.draftPost(
        { patch: { scenes: { [sceneName]: scenePatch } } },
        { successMsg: `Updated ${sceneName}` }
      );
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
      const proceed = await this.openConfirmModal({
        title: `Remove '${sceneName}' from this bank?`,
        message: "It stays in the config but won't fire from this stage anymore.",
        confirmText: 'Remove',
        danger: true,
      });
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
      const values = await this.openPromptModal({
        title: 'Add scene to this bank',
        message: 'Pick a MIDI note (0–127). If the pad already has a scene, that existing scene will be shared into this bank.',
        confirmText: 'Add scene',
        fields: [{ name: 'note', label: 'MIDI note', value: '', type: 'number', min: 0, max: 127, step: 1 }],
        validate: (input) => {
          const note = Number(input.note);
          if (!Number.isFinite(note) || note < 0 || note > 127) return 'MIDI note must be 0–127.';
          return '';
        },
      });
      if (!values) return;
      const note = Number(values.note);
      if (!Number.isFinite(note) || note < 0 || note > 127) {
        this.statusText = 'MIDI note must be 0–127.';
        return;
      }
      const personality = this.drawerPersonalityName();
      const role = this.drawer.role || this.currentBank()?.default_role || 'groove';
      const [, bankField] = this._roleSceneFields(role);
      const bankChannel = Number(this.currentBank()?.channel || 1);
      // If a scene already exists at this note+channel globally, share it into
      // this personality's role bank instead of creating a duplicate.
      let existingSceneName = '';
      const scenes = this.config?.scenes || {};
      for (const [sName, sObj] of Object.entries(scenes)) {
        const sMidi = sObj?.midi || {};
        if (Number(sMidi.note) === note && Number(sMidi.channel ?? 1) === bankChannel) {
          existingSceneName = sName;
          break;
        }
      }
      if (existingSceneName) {
        const pdata = this.config?.personalities?.[personality] || {};
        const existingBank = Array.isArray(pdata[bankField]) ? [...pdata[bankField]] : [];
        if (existingBank.includes(existingSceneName)) {
          this.statusText = `${existingSceneName} is already in ${personality}:${role} bank.`;
          return;
        }
        const patch = {
          personalities: {
            [personality]: {
              [bankField]: [...existingBank, existingSceneName],
            },
          },
        };
        await this.draftPost(
          { patch },
          { successMsg: `Shared ${existingSceneName} into ${personality}:${role} bank` },
        );
        return;
      }
      const result = await this.draftPost({
        mapping: {
          personality,
          role,
          note,
          channel: bankChannel,
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
      });
      if (result.ok) {
        this.statusText = `Added ${result.data.scene_name || `note ${note}`} to ${role} bank`;
      }
    },



    async applyPatch(patch, successMsg) {
      const result = await this.draftPost({ patch }, { successMsg });
      return result.ok;
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
        const proceed = await this.openConfirmModal({
          title: 'Move pad to different channel?',
          message: `Pad ${note} will move from Ch${sourceChannel} to ${targetBank.name} Ch${targetChannel}. The scene MIDI channel will be updated.`,
          confirmText: 'Move',
        });
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



    syncTimingDraft() {
      const pdata = this.personalityData();
      this.timingDraft = {
        phrase_interval_beats: Number(pdata?.phrase_interval_beats ?? 32),
        minimum_scene_hold_beats: Number(pdata?.minimum_scene_hold_beats ?? 8),
        buildup_lookahead_beats: Number(pdata?.buildup_lookahead_beats ?? 32),
        pre_drop_blackout_beats: Number(pdata?.pre_drop_blackout_beats ?? 4),
        post_drop_hold_beats: Number(pdata?.post_drop_hold_beats ?? 8),
        breakdown_default_restore_beats: Number(pdata?.breakdown_default_restore_beats ?? 64),
      };
    },



    syncPersonalityDrafts() {
      const pdata = this.personalityData();
      const aliases = Array.isArray(pdata?.aliases) ? pdata.aliases : [];
      this.aliasesDraft = { text: aliases.join('\n') };
      this.bpmBandDraft = {
        min: Number(pdata?.bpm_band_min ?? 0),
        max: Number(pdata?.bpm_band_max ?? 0),
      };
      this.syncTimingDraft();
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
            pre_drop_blackout_beats: Number(this.timingDraft.pre_drop_blackout_beats),
            post_drop_hold_beats: Number(this.timingDraft.post_drop_hold_beats),
            breakdown_default_restore_beats: Number(this.timingDraft.breakdown_default_restore_beats),
          },
        },
      };
      await this.draftPost({ patch }, { successMsg: `Saved timing for ${personality}` });
    },



    async commitDraft() {
      this.markSaving();
      try {
        const response = await fetch('/api/commit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const data = await response.json();
        if (data.ok) {
          this.statusText = 'Saved & applied';
          await this.refreshConfig();
          this.lastCommittedHash = this.currentConfigHash;
          this.markSaved();
          this.saveState.applied = true;
        } else {
          const msg = `Save failed: ${(data.errors || []).join('; ')}`;
          this.statusText = msg;
          this.markSaveError(msg);
        }
      } catch (err) {
        const msg = `Save failed: ${err.message}`;
        this.statusText = msg;
        this.markSaveError(msg);
      }
    },



    async discardDraftConfirm() {
      const proceed = await this.openConfirmModal({
        title: 'Discard draft changes?',
        message: 'Reverts all unapplied edits to the last applied config.',
        confirmText: 'Discard',
        danger: true,
      });
      if (!proceed) return;
      await this.discardDraft();
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
        this.lastCommittedHash = this.currentConfigHash;
        this.statusText = 'Unsaved changes discarded';
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
        this.statusText = `System checks: ${errors.length} error(s), ${warnings.length} warning(s), ${failed}/${checks.length} live tests failed`;
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
          this.statusText = data?.error || 'Send test failed';
          return;
        }
        this.statusText = `Sent pad ${Number(note)} on channel ${Number(channel)}`;
      } catch (err) {
        this.statusText = `Send test failed: ${err.message}`;
      }
    },


    // Add or remove this pad's scene from the active personality's role bank
    // (the bank for whichever role the scene is currently classified as).
    // Triggered by cmd/ctrl + left click on a mapped, non-system pad.
    async togglePadInActivePersonality(note) {
      const meta = this.sceneDetailsByNote(note);
      if (!meta.mapped || meta.system || !meta.sceneName) {
        this.statusText = `Note ${note} is unmapped or system; nothing to add.`;
        return;
      }
      const personality = this.activePersonality();
      const personalities = this.config?.personalities || {};
      const pdata = personalities[personality];
      if (!pdata || typeof pdata !== 'object') {
        this.statusText = `Active personality "${personality}" not found.`;
        return;
      }
      const role = meta.role || this.currentBank()?.default_role || 'groove';
      const fields = ROLE_FIELDS[role];
      if (!fields) {
        this.statusText = `Unknown role "${role}" for note ${note}.`;
        return;
      }
      const bankField = fields[1];
      const sceneName = meta.sceneName;
      const existing = Array.isArray(pdata[bankField]) ? pdata[bankField] : [];
      let updatedBank;
      let action;
      if (existing.includes(sceneName)) {
        updatedBank = existing.filter((s) => s !== sceneName);
        action = 'Removed from';
      } else {
        updatedBank = [...existing, sceneName];
        action = 'Added to';
      }
      await this.draftPost(
        {
          patch: {
            personalities: {
              [personality]: {
                [bankField]: updatedBank,
              },
            },
          },
        },
        { successMsg: `${action} ${personality}:${role} → ${sceneName}` }
      );
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
      await this.draftPost(
        { patch },
        { successMsg: `Primary ${meta.role} mapping set to ${meta.sceneName}` }
      );
    },



    async removeDrawerMapping() {
      if (this.openNote === null || this.openNote === undefined) return;
      const meta = this.drawerSceneDetails();
      if (!meta.mapped || !meta.sceneName || !meta.role) return;
      const proceed = await this.openConfirmModal({
        title: `Remove mapping for '${meta.sceneName}'?`,
        message: 'The scene definition stays. Only the pad-to-scene mapping goes away.',
        confirmText: 'Remove',
        danger: true,
      });
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
      const result = await this.draftPost(
        { patch },
        { successMsg: `Removed mapping ${meta.sceneName}` }
      );
      if (result.ok) this.openNote = null;
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
      this.markSaving();
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
        const personality = this.drawer.personality;
        const note = Number(this.openNote);
        const channel = Number(this.currentBank()?.channel || 1);
        const roleChanged = this.drawerRoleChanged();

        // For role changes, do a clean bank MOVE: relocate the existing scene
        // between role banks (no new scene created, no primary hijacked). Plus
        // update scene MIDI/properties in the same patch.
        if (roleChanged) {
          const meta = this.drawerSceneDetails();
          const sceneName = meta?.sceneName || '';
          const oldRole = meta?.role || '';
          const newRole = String(this.drawer.role || '');
          if (sceneName && oldRole && newRole && oldRole !== newRole) {
            const [oldSceneField, oldBankField] = this._roleSceneFields(oldRole);
            const [newSceneField, newBankField] = this._roleSceneFields(newRole);
            if (oldSceneField && oldBankField && newSceneField && newBankField) {
              const pdata = this.config?.personalities?.[personality] || {};
              const oldBank = Array.isArray(pdata[oldBankField]) ? [...pdata[oldBankField]] : [];
              const newBank = Array.isArray(pdata[newBankField]) ? [...pdata[newBankField]] : [];
              const wasPrimary = pdata[oldSceneField] === sceneName;
              const filteredOldBank = oldBank.filter((n) => n !== sceneName);
              const mergedNewBank = newBank.includes(sceneName) ? newBank : [...newBank, sceneName];
              const personalityPatch = {
                [oldBankField]: filteredOldBank,
                [newBankField]: mergedNewBank,
              };
              if (wasPrimary) {
                personalityPatch[oldSceneField] = filteredOldBank[0] || '';
                if (oldRole === 'groove') {
                  personalityPatch.default_scene = filteredOldBank[0] || '';
                }
              }
              const scenes = this.config?.scenes || {};
              const existingScene = scenes[sceneName] || {};
              const existingMidi = existingScene.midi || {};
              const updatedScene = {
                ...existingScene,
                safety_class: this.drawer.safety_class,
                immediate: Boolean(this.drawer.immediate),
                cooldown_beats: Number(this.drawer.cooldown_beats),
                midi: {
                  ...existingMidi,
                  note,
                  channel,
                  velocity: Number(this.drawer.velocity),
                  behavior: effectiveBehavior,
                  hold_beats: Number(this.drawer.hold_beats),
                  duration_ms: Number(this.drawer.duration_ms),
                },
              };
              const patch = {
                scenes: { [sceneName]: updatedScene },
                personalities: { [personality]: personalityPatch },
              };
              const result = await this.draftPost(
                { patch },
                { successMsg: `Moved ${sceneName} from ${oldRole} to ${newRole}` },
              );
              if (result.ok) {
                this.statusText = `Moved ${sceneName} to ${newRole} bank`;
              }
              return;
            }
          }
        }

        // Same-role edits (or no existing scene): existing apply_mapping flow.
        // Auto-save must never replace_primary — that's reserved for the explicit
        // "Set as primary" button (setDrawerPrimary).
        const payload = {
          mapping: {
            personality,
            role: this.drawer.role,
            note,
            channel,
            velocity: Number(this.drawer.velocity),
            behavior: effectiveBehavior,
            hold_beats: Number(this.drawer.hold_beats),
            duration_ms: Number(this.drawer.duration_ms),
            cooldown_beats: Number(this.drawer.cooldown_beats),
            safety_class: this.drawer.safety_class,
            immediate: Boolean(this.drawer.immediate),
            label: this.drawer.label,
            add_to_bank: false,
            replace_primary: false,
          },
        }
        const result = await this.draftPost(payload);
        if (result.ok) {
          this.statusText = `Draft updated${result.data.scene_name ? ` (${result.data.scene_name})` : ''}`;
        }
      } catch (err) {
        this.statusText = `Drawer apply failed: ${err.message}`;
        this.markSaveError(this.statusText);
      }
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
      const result = await this.draftPost({ patch });
      if (result.ok) {
        this.armReassignUndo(sourceBefore, targetBefore, sourceNote, targetNote);
        this.statusText = allowSwap
          ? `Swapped note ${sourceNote} with ${targetNote}`
          : `Moved mapping ${sourceNote} → ${targetNote}`;
      }
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
      await this.draftPost({ patch }, { successMsg: 'Reassign undone' });
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
      await this.draftPost(
        { patch: { manual_commands: { [slot]: message } } },
        { successMsg: `${slot} saved` }
      );
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
      await this.draftPost(
        { patch: { _pad_meta: { banks } } },
        { successMsg: `Bank ${index + 1} ${field} updated` }
      );
    },



    async resetBanksToDefault() {
      const proceed = await this.openConfirmModal({
        title: 'Reset all banks?',
        message: 'All banks return to the default 4 × 32 layout. Custom names and MIDI channels will be lost.',
        confirmText: 'Reset',
        danger: true,
      });
      if (!proceed) return;
      this.markSaving();
      try {
        const response = await fetch('/api/banks/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const data = await response.json();
        if (!data.ok) {
          const msg = data.error || 'Reset banks failed';
          this.statusText = msg;
          this.markSaveError(msg);
          return;
        }
        this.statusText = 'Banks reset to default (4 × 32)';
        await this.refreshConfig();
        this.markSaved();
      } catch (err) {
        const msg = `Reset banks failed: ${err.message}`;
        this.statusText = msg;
        this.markSaveError(msg);
      }
    },



    async clearBlackout(which) {
      const slot = which === 'on' ? 'blackout_on' : 'blackout_off';
      await this.draftPost(
        { patch: { manual_commands: { [slot]: null } } },
        { successMsg: `${slot} cleared` }
      );
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
      const proceed = await this.openConfirmModal({
        title: `Restore '${this.historySelected.name}'?`,
        message: 'Loads this backup as your unsaved draft. You can still Save & Apply or Discard.',
        confirmText: 'Restore',
      });
      if (!proceed) return;
      this.markSaving();
      try {
        const response = await fetch(`/api/history/${this.historySelected.name}/restore`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const data = await response.json();
        if (!response.ok) {
          const msg = data.error || 'Restore failed';
          this.statusText = msg;
          this.markSaveError(msg);
          return;
        }
        this.statusText = `Restored ${this.historySelected.name} to draft`;
        await this.refreshConfig();
        await this.loadHistory();
        this.markSaved();
      } catch (err) {
        const msg = `Restore failed: ${err.message}`;
        this.statusText = msg;
        this.markSaveError(msg);
      }
    }
  };
})(window.LaserPad);

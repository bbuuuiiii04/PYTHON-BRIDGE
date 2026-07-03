window.LaserPad = window.LaserPad || {};

(function laserPadModule(ns) {
  const ROLE_FIELDS = ns.ROLE_FIELDS;
  const BANK_ROLES = ns.BANK_ROLES;
  const PERSONALITY_COLOR_PALETTE = ns.PERSONALITY_COLOR_PALETTE;
  const hardDuplicateMap = ns.hardDuplicateMap;

  ns.selectors = {


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



    configHash(config) {
      try {
        return JSON.stringify(config || {});
      } catch (_err) {
        return '';
      }
    },


    /**
     * True when the current draft hash differs from the draft hash at the last
     * successful commit (or first page load if nothing has been committed yet).
     * This is a page-session approximation, not a disk vs draft comparison.
     */
    hasUnsavedChanges() {
      return Boolean(this.currentConfigHash && this.lastCommittedHash && this.currentConfigHash !== this.lastCommittedHash);
    },



    saveBadgeClass() {
      return `save-badge ${this.saveState.kind}`;
    },



    saveBadgeText() {
      if (this.saveState.kind === 'saving') return 'Saving…';
      if (this.saveState.kind === 'error') return this.saveState.lastError || 'Save failed';
      const label = this.saveState.applied ? 'Applied' : 'Draft saved';
      if (this.saveState.timestamp) return `${label} ${this.saveState.timestamp}`;
      return label;
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



    displayPersonalityName(name) {
      return String(name || '').replace(/_/g, ' ');
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



    /**
     * Memoized by currentConfigHash/note/personality. refreshConfig() replaces
     * the config hash and clears _selectorCache after each config reload.
     */
    sceneDetailsByNote(note, personalityName = this.activePersonality()) {
      const cache = this._selectorCache instanceof Map ? this._selectorCache : null;
      const cacheKey = `sceneDetailsByNote:${this.currentConfigHash}:${this.activeBankId}:${note}:${personalityName}`;
      if (cache?.has(cacheKey)) return cache.get(cacheKey);
      const remember = (value) => {
        cache?.set(cacheKey, value);
        return value;
      };
      const personalities = this.config?.personalities || {};
      const pdata = personalities[personalityName] || {};
      const scenes = this.config?.scenes || {};
      const bank = this.currentBank();
      const bankChannel = Number(bank?.channel || 1);
      const bankRole = String(bank?.default_role || '');
      const manual = this.config?.manual_commands || {};

      for (const slot of ['blackout_on', 'blackout_off']) {
        const cmd = manual[slot];
        if (cmd && Number(cmd.channel ?? 1) === bankChannel && Number(cmd.note) === Number(note)) {
          return remember({
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
          });
        }
      }

      const ROLE_FIELD_TUPLES = [
        ['groove', 'phrase_scene', 'phrase_bank'],
        ['buildup', 'buildup_scene', 'buildup_bank'],
        ['drop', 'drop_scene', 'drop_bank'],
        ['post_drop', 'post_drop_scene', 'post_drop_bank'],
        ['breakdown', 'breakdown_scene', 'breakdown_bank'],
      ];

      // Pass 1: prefer the ACTIVE personality's role banks (role order: groove,
      // buildup, drop, post_drop, breakdown). Preserves the original role/primary
      // labeling when the active personality references the scene.
      for (const [role, sceneField, bankField] of ROLE_FIELD_TUPLES) {
        const names = [];
        if (typeof pdata[sceneField] === 'string' && pdata[sceneField]) {
          names.push(pdata[sceneField]);
        }
        const bankList = Array.isArray(pdata[bankField]) ? pdata[bankField] : [];
        bankList.forEach((sceneName) => {
          if (typeof sceneName === 'string' && sceneName && !names.includes(sceneName)) {
            names.push(sceneName);
          }
        });
        for (const sceneName of names) {
          const scene = scenes[sceneName] || {};
          const midi = scene.midi || {};
          if (Number(midi.note) === Number(note) && Number(midi.channel ?? 1) === bankChannel) {
            return remember({
              role,
              sceneName,
              mapped: true,
              primary: pdata[sceneField] === sceneName,
              safetyClass: scene.safety_class || 'safe',
              label: scene.label || '',
              channel: Number(midi.channel ?? 1),
              personality: this.activePersonality(),
              behavior: midi.behavior || 'pulse',
              velocity: Number(midi.velocity ?? 127),
              hold_beats: Number(midi.hold_beats ?? bank?.default_hold_beats ?? 4),
              duration_ms: Number(midi.duration_ms ?? bank?.default_duration_ms ?? 80),
              cooldown_beats: Number(scene.cooldown_beats ?? bank?.default_cooldown_beats ?? 8),
              immediate: Boolean(scene.immediate),
              system: false,
            });
          }
        }
      }

      // Pass 2: global fallback so switching personality never "wipes" a mapped
      // pad. When multiple scenes share the same note+channel, prefer the one
      // referenced in the DEFAULT personality's role banks, then any
      // personality's role banks, then the first match.
      const matches = [];
      for (const [sName, sObj] of Object.entries(scenes)) {
        const sMidi = sObj?.midi || {};
        if (Number(sMidi.note) !== Number(note) || Number(sMidi.channel ?? 1) !== bankChannel) continue;
        matches.push([sName, sObj]);
      }
      if (matches.length) {
        const defaultName = String(this.config?.default_personality || '');
        const defaultPdata = personalities[defaultName] || {};
        const inPersonalityRoles = (sceneName, pData) => {
          if (!pData || typeof pData !== 'object') return '';
          for (const [r, sField, bField] of ROLE_FIELD_TUPLES) {
            const bList = Array.isArray(pData[bField]) ? pData[bField] : [];
            if (pData[sField] === sceneName || bList.includes(sceneName)) return r;
          }
          return '';
        };
        let chosen = null;
        let chosenRole = '';
        // Preference 1: default personality's role banks
        for (const m of matches) {
          const r = inPersonalityRoles(m[0], defaultPdata);
          if (r) { chosen = m; chosenRole = r; break; }
        }
        // Preference 2: any personality's role banks
        if (!chosen) {
          for (const m of matches) {
            for (const pData of Object.values(personalities)) {
              const r = inPersonalityRoles(m[0], pData);
              if (r) { chosen = m; chosenRole = r; break; }
            }
            if (chosen) break;
          }
        }
        // Last resort: first match
        if (!chosen) chosen = matches[0];
        const [sceneName, scene] = chosen;
        const midi = scene?.midi || {};
        return remember({
          role: chosenRole || bankRole,
          sceneName,
          mapped: true,
          primary: false,
          safetyClass: scene.safety_class || 'safe',
          label: scene.label || '',
          channel: Number(midi.channel ?? 1),
          personality: this.activePersonality(),
          behavior: midi.behavior || 'pulse',
          velocity: Number(midi.velocity ?? 127),
          hold_beats: Number(midi.hold_beats ?? bank?.default_hold_beats ?? 4),
          duration_ms: Number(midi.duration_ms ?? bank?.default_duration_ms ?? 80),
          cooldown_beats: Number(scene.cooldown_beats ?? bank?.default_cooldown_beats ?? 8),
          immediate: Boolean(scene.immediate),
          system: false,
        });
      }

      return remember({
        role: '',
        sceneName: '',
        mapped: false,
        primary: false,
        safetyClass: 'safe',
        label: this.unmappedLabel(note),
        channel: bankChannel,
        personality: this.activePersonality(),
        behavior: bank?.default_behavior || 'pulse',
        velocity: 127,
        hold_beats: Number(bank?.default_hold_beats || 4),
        duration_ms: Number(bank?.default_duration_ms || 80),
        cooldown_beats: Number(bank?.default_cooldown_beats || 8),
        immediate: false,
        system: false,
      });
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



    padInActivePersonality(note) {
      const meta = this.sceneMetaByNote(note);
      if (!meta.mapped || meta.system || !meta.sceneName) return false;
      const personality = this.activePersonality();
      const pdata = this.config?.personalities?.[personality] || {};
      for (const [sceneField, bankField] of Object.values(ROLE_FIELDS)) {
        if (pdata[sceneField] === meta.sceneName) return true;
        const bank = Array.isArray(pdata[bankField]) ? pdata[bankField] : [];
        if (bank.includes(meta.sceneName)) return true;
      }
      return false;
    },


    // Stable color for a personality. Honors explicit overrides stored in
    // _pad_meta.personality_colors[name].color first; otherwise auto-assigns
    // from PERSONALITY_COLOR_PALETTE in alphabetical order, skipping colors
    // already claimed by overrides so each personality gets a unique color
    // when count <= palette.length.
    personalityColor(name) {
      const overrides = this.config?._pad_meta?.personality_colors || {};
      const explicit = overrides[name]?.color;
      if (typeof explicit === 'string' && /^#[0-9a-fA-F]{6}$/.test(explicit)) {
        return explicit;
      }
      const personalities = this.config?.personalities || {};
      const names = Object.keys(personalities).sort();
      if (!names.includes(name)) {
        // Unknown personality (e.g., transient state); fall back to a stable
        // hash so we never return undefined.
        let h = 0;
        for (let i = 0; i < name.length; i++) {
          h = ((h << 5) - h + name.charCodeAt(i)) | 0;
        }
        return PERSONALITY_COLOR_PALETTE[Math.abs(h) % PERSONALITY_COLOR_PALETTE.length];
      }
      const used = new Set();
      for (const pname of names) {
        const c = overrides[pname]?.color;
        if (typeof c === 'string' && /^#[0-9a-fA-F]{6}$/.test(c)) used.add(c.toLowerCase());
      }
      let paletteIdx = 0;
      for (const pname of names) {
        if (overrides[pname]?.color) continue;
        while (
          paletteIdx < PERSONALITY_COLOR_PALETTE.length &&
          used.has(PERSONALITY_COLOR_PALETTE[paletteIdx].toLowerCase())
        ) {
          paletteIdx++;
        }
        const color = PERSONALITY_COLOR_PALETTE[paletteIdx % PERSONALITY_COLOR_PALETTE.length];
        if (pname === name) return color;
        used.add(color.toLowerCase());
        paletteIdx++;
      }
      return PERSONALITY_COLOR_PALETTE[0];
    },



    personalityInitials(name) {
      const overrides = this.config?._pad_meta?.personality_colors || {};
      const explicit = overrides[name]?.initial;
      if (typeof explicit === 'string' && explicit.trim()) {
        return explicit.trim().toUpperCase().slice(0, 3);
      }
      const str = String(name || '').trim();
      if (!str) return '?';
      return str.slice(0, 2).toUpperCase();
    },


    /**
     * Returns one chip per personality whose role banks/primaries reference
     * the scene mapped to this note. Memoized by currentConfigHash/note;
     * refreshConfig() clears _selectorCache after each config reload.
     */
    personalityChipsForNote(note) {
      const cache = this._selectorCache instanceof Map ? this._selectorCache : null;
      const cacheKey = `personalityChipsForNote:${this.currentConfigHash}:${this.activeBankId}:${note}`;
      if (cache?.has(cacheKey)) return cache.get(cacheKey);
      const remember = (value) => {
        cache?.set(cacheKey, value);
        return value;
      };
      const meta = this.sceneMetaByNote(note);
      if (!meta.mapped || meta.system || !meta.sceneName) return remember([]);
      const personalities = this.config?.personalities || {};
      const sceneName = meta.sceneName;
      const active = this.activePersonality();
      const matches = [];
      for (const [pname, pdata] of Object.entries(personalities)) {
        if (!pdata || typeof pdata !== 'object') continue;
        let referenced = false;
        for (const [sceneField, bankField] of Object.values(ROLE_FIELDS)) {
          if (pdata[sceneField] === sceneName) { referenced = true; break; }
          const bank = Array.isArray(pdata[bankField]) ? pdata[bankField] : [];
          if (bank.includes(sceneName)) { referenced = true; break; }
        }
        if (!referenced) continue;
        matches.push({
          name: pname,
          initial: this.personalityInitials(pname),
          color: this.personalityColor(pname),
          isActive: pname === active,
        });
      }
      matches.sort((a, b) => {
        if (a.isActive && !b.isActive) return -1;
        if (!a.isActive && b.isActive) return 1;
        return a.name.localeCompare(b.name);
      });
      return remember(matches);
    },



    // firingNote/pressProgress.note start out `null`. Number(null) is 0, so
    // without the explicit null guard, MIDI note 0 (a real, valid pad — bank 1
    // starts at note 0) would render as permanently firing/pressing from page
    // load, before anything ever fired.
    isFiring(note) {
      return this.firingNote !== null && Number(this.firingNote) === Number(note);
    },



    // Single string-returning class binding. The bundled Alpine build does
    // not merge mixed string+object arrays passed to :class (it falls back
    // to a naive String(array) and literally renders "[object Object]"), so
    // this pre-joins everything into one space-separated string instead of
    // handing Alpine `[roleClass(note), {...}]`.
    tileClasses(note) {
      const classes = [];
      const role = this.roleClass(note);
      if (role) classes.push(role);
      const mapped = this.isMapped(note);
      const inActive = this.padInActivePersonality(note);
      if (mapped) classes.push('mapped');
      if (inActive) classes.push('in-active-personality');
      if (mapped && !inActive && !this.sceneMetaByNote(note).system) classes.push('pad-dim');
      if (this.isDropTarget(note)) classes.push('drop-target');
      if (this.isFiring(note)) classes.push('firing');
      if (this.isPressing(note)) classes.push('pressing');
      if (this.verifyState(note)?.ok === false) classes.push('verify-fail');
      return classes.join(' ');
    },



    isPressing(note) {
      return this.pressProgress.note !== null && Number(this.pressProgress.note) === Number(note);
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
      const refs = this.personalitiesUsingScene(meta.sceneName);
      const usageText = refs.length ? `Used by:\n  ${refs.join('\n  ')}` : 'Not used by any personality';
      return [
        `${meta.sceneName} · ch${meta.channel} · note${note} · ${meta.behavior} ${duration}`,
        verifyText,
        usageText,
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
      const distinctSceneNames = (refs) => new Set(
        refs
          .map((ref) => String(ref.sceneName || ref.scene_name || ''))
          .filter(Boolean)
      );
      const serverHard = Array.isArray(this.hardDuplicates)
        ? this.hardDuplicates.filter((row) => Array.isArray(row.refs) && distinctSceneNames(row.refs).size > 1)
        : [];
      if (serverHard.length) {
        const first = serverHard[0];
        return `Duplicate mapping on ${first.channel}:${first.note} across ${distinctSceneNames(first.refs).size} scenes`;
      }
      const hard = hardDuplicateMap(this.config);
      const dupes = Array.from(hard.entries()).filter(([, refs]) => distinctSceneNames(refs).size > 1);
      if (!dupes.length) return '';
      const [key, refs] = dupes[0];
      return `Duplicate mapping on ${key} across ${distinctSceneNames(refs).size} scenes`;
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



    bankRoleDefinitions() {
      return BANK_ROLES;
    },



    sceneNote(sceneName) {
      const note = this.config?.scenes?.[sceneName]?.midi?.note;
      return Number.isFinite(Number(note)) ? Number(note) : '?';
    },



    isScenePreferredForRole(role, sceneName) {
      const sceneType = String(this.config?.scenes?.[sceneName]?.scene_type || '');
      if (role === 'breakdown') {
        return sceneType === 'autoloop' || sceneType === 'static';
      }
      if (['groove', 'buildup', 'drop', 'post_drop'].includes(role)) {
        return sceneType === 'autoloop';
      }
      return false;
    },



    sceneOptionsForRole(role) {
      return this.availableScenes().sort((left, right) => {
        const leftPreferred = this.isScenePreferredForRole(role, left) ? 0 : 1;
        const rightPreferred = this.isScenePreferredForRole(role, right) ? 0 : 1;
        if (leftPreferred !== rightPreferred) return leftPreferred - rightPreferred;
        return left.localeCompare(right);
      });
    },



    smartDropModes() {
      return ['blackout_mask', 'legacy_rearm'];
    },



    parseAliasesDraft() {
      return String(this.aliasesDraft.text || '')
        .split(/[\n,]+/)
        .map((alias) => alias.trim())
        .filter(Boolean);
    },



    aliasSummary(name) {
      const aliases = this.config?.personalities?.[name]?.aliases;
      if (!Array.isArray(aliases) || !aliases.length) return 'no aliases';
      return aliases.join(', ');
    },



    formatBpm(value) {
      const num = Number(value);
      if (!Number.isFinite(num)) return '0';
      return Number.isInteger(num) ? String(num) : String(Number(num.toFixed(2)));
    },



    personalityMatchSummary() {
      const pdata = this.personalityData();
      const aliases = Array.isArray(pdata?.aliases)
        ? pdata.aliases.map((alias) => String(alias || '').trim()).filter(Boolean)
        : [];
      const aliasText = aliases.length
        ? `Matches playlists containing: ${aliases.join(', ')}.`
        : 'Matches no playlist names.';
      const min = Number(pdata?.bpm_band_min ?? 0);
      const max = Number(pdata?.bpm_band_max ?? 0);
      const bpmText = Number.isFinite(min) && Number.isFinite(max) && min > 0 && max > 0 && min < max
        ? `BPM ${this.formatBpm(min)}-${this.formatBpm(max)} when no playlist matches.`
        : 'no BPM fallback configured.';
      return `${aliasText} ${bpmText}`;
    },



    personalityPrimaryScene(role) {
      const [sceneField] = this._roleSceneFields(role);
      const value = sceneField ? this.personalityData()?.[sceneField] : '';
      return typeof value === 'string' ? value : '';
    },



    personalityBankFor(role) {
      const [_sceneField, bankField] = this._roleSceneFields(role);
      const bank = bankField ? this.personalityData()?.[bankField] : [];
      if (!Array.isArray(bank)) return [];
      return bank
        .map((sceneName) => String(sceneName || '').trim())
        .filter((sceneName, index, list) => sceneName && list.indexOf(sceneName) === index);
    },



    bankWarningForRole(role) {
      const primary = this.personalityPrimaryScene(role);
      const bank = this.personalityBankFor(role);
      const scenes = this.config?.scenes || {};
      if (primary && !scenes[primary]) {
        return 'primary scene is missing from global scenes';
      }
      if (!bank.length) {
        return 'bank list is empty - this role will fall back instead of rotating';
      }
      if (primary && !bank.includes(primary)) {
        return 'primary scene not in bank list - rotation will start from a scene not in this bank';
      }
      return '';
    },



    canSaveAliasesDraft() {
      const aliases = this.parseAliasesDraft();
      return aliases.every((alias) => alias.length > 0);
    },



    canSaveBpmBandDraft() {
      const min = Number(this.bpmBandDraft.min);
      const max = Number(this.bpmBandDraft.max);
      return Number.isFinite(min) && Number.isFinite(max) && min >= 0 && max >= 0
        && ((min === 0 && max === 0) || min < max);
    },



    resolverTestLabel() {
      const result = this.resolverTest.result;
      if (!result) return '';
      const matched = result.matched ? ` · matched ${result.matched}` : '';
      return `${result.personality || '(none)'} · ${result.reason}${matched}`;
    },



    lifecycleSceneLabel(field) {
      const labels = {
        startup_scene: 'When laser bridge starts',
        stop_scene: 'When laser bridge stops',
        stale_scene: 'When music data goes silent',
        emergency_scene: 'Emergency / panic',
        fallback_scene: 'Default backup scene',
      };
      return labels[String(field || '')] || String(field || '');
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



    personalitiesUsingScene(sceneName) {
      const target = String(sceneName || '');
      if (!target) return [];
      const refs = [];
      // Top-level config scene slots (startup, stop, stale, emergency, fallback).
      const TOP_LEVEL_SCENE_FIELDS = [
        'startup_scene',
        'stop_scene',
        'stale_scene',
        'emergency_scene',
        'fallback_scene',
      ];
      TOP_LEVEL_SCENE_FIELDS.forEach((field) => {
        if (this.config?.[field] === target) {
          refs.push(`config:${field.replace('_scene', '')}`);
        }
      });
      // Per-personality references: role primaries, role banks, and utility slots.
      const PERSONALITY_UTILITY_FIELDS = [
        'safe_scene',
        'default_scene',
        'transition_scene',
        'pre_drop_scene',
      ];
      const personalities = this.config?.personalities || {};
      Object.entries(personalities).forEach(([personality, pdata]) => {
        if (!pdata || typeof pdata !== 'object') return;
        Object.entries(ROLE_FIELDS).forEach(([role, [sceneField, bankField]]) => {
          const primary = pdata[sceneField] === target;
          const bank = Array.isArray(pdata[bankField]) ? pdata[bankField] : [];
          if (primary) refs.push(`${personality}:${role}:primary`);
          if (bank.includes(target)) refs.push(`${personality}:${role}:bank`);
        });
        PERSONALITY_UTILITY_FIELDS.forEach((field) => {
          if (pdata[field] === target) {
            refs.push(`${personality}:${field.replace('_scene', '')}`);
          }
        });
      });
      return refs;
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



    rawSceneJson(note) {
      const meta = this.sceneDetailsByNote(note);
      if (!meta.sceneName) return '{}';
      return JSON.stringify(this.config?.scenes?.[meta.sceneName] || {}, null, 2);
    },



    canSaveTimingDraft() {
      const phrase = Number(this.timingDraft.phrase_interval_beats);
      const hold = Number(this.timingDraft.minimum_scene_hold_beats);
      const lookahead = Number(this.timingDraft.buildup_lookahead_beats);
      const preDrop = Number(this.timingDraft.pre_drop_blackout_beats);
      const postDrop = Number(this.timingDraft.post_drop_hold_beats);
      const breakdown = Number(this.timingDraft.breakdown_default_restore_beats);
      return Number.isFinite(phrase) && phrase >= 1
        && Number.isFinite(hold) && hold >= 0
        && Number.isFinite(lookahead) && lookahead >= 1
        && Number.isFinite(preDrop) && preDrop >= 0
        && Number.isFinite(postDrop) && postDrop >= 0
        && Number.isFinite(breakdown) && breakdown >= 0;
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
      return ROLE_FIELDS[role] || ['', ''];
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



    isDropTarget(note) {
      return this.draggedNote !== null && this.dropTargetNote === note;
    },



    blackoutConfigured(which) {
      const manual = this.config?.manual_commands || {};
      const key = which === 'on' ? 'blackout_on' : 'blackout_off';
      return !!manual[key];
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
    }
  };
})(window.LaserPad);

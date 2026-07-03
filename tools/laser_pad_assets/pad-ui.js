window.LaserPad = window.LaserPad || {};

(function laserPadModule(ns) {
  const ROLE_FIELDS = ns.ROLE_FIELDS;
  const BANK_ROLES = ns.BANK_ROLES;
  const PERSONALITY_COLOR_PALETTE = ns.PERSONALITY_COLOR_PALETTE;
  const hardDuplicateMap = ns.hardDuplicateMap;

  ns.ui = {


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



    openPromptModal(options) {
      return new Promise((resolve) => {
        const opts = options || {};
        this.modal = {
          open: true,
          type: 'prompt',
          title: String(opts.title || ''),
          message: String(opts.message || ''),
          fields: Array.isArray(opts.fields) ? opts.fields.map((field) => ({
            name: String(field.name || ''),
            label: String(field.label || ''),
            value: String(field.value ?? ''),
            type: String(field.type || 'text'),
            placeholder: String(field.placeholder || ''),
            min: field.min,
            max: field.max,
            step: field.step,
          })) : [],
          error: '',
          confirmText: String(opts.confirmText || 'Save'),
          cancelText: String(opts.cancelText || 'Cancel'),
          danger: false,
          validate: typeof opts.validate === 'function' ? opts.validate : null,
        };
        this.modalResolver = resolve;
      });
    },



    openConfirmModal(options) {
      return new Promise((resolve) => {
        const opts = options || {};
        this.modal = {
          open: true,
          type: 'confirm',
          title: String(opts.title || ''),
          message: String(opts.message || ''),
          fields: [],
          error: '',
          confirmText: String(opts.confirmText || 'Confirm'),
          cancelText: String(opts.cancelText || 'Cancel'),
          danger: Boolean(opts.danger),
          validate: null,
        };
        this.modalResolver = resolve;
      });
    },



    closeModal(result = null) {
      if (!this.modal.open) return;
      const resolve = this.modalResolver;
      this.modalResolver = null;
      this.modal = {
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
      };
      if (typeof resolve === 'function') {
        resolve(result);
      }
    },



    submitModalPrompt() {
      if (!this.modal.open || this.modal.type !== 'prompt') return;
      const values = {};
      this.modal.fields.forEach((field) => {
        values[field.name] = field.value;
      });
      if (typeof this.modal.validate === 'function') {
        const error = this.modal.validate(values);
        if (error) {
          this.modal.error = String(error);
          return;
        }
      }
      this.closeModal(values);
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
      // Cmd+click (mac) / Ctrl+click (win/linux): toggle membership of this
      // pad's scene in the active personality's role bank. Don't fire the
      // scene; this is a config edit, not a test trigger.
      if (event && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        this.togglePadInActivePersonality(note);
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



    dropOn(note, event) {
      if (this.draggedNote === null) return;
      event.preventDefault();
      const sourceNote = this.draggedNote;
      this.dragEnd();
      this.reassignNoteTo(sourceNote, note);
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



    openHistoryPanel() {
      this.historyOpen = true;
      this.loadHistory();
    },



    closeHistoryPanel() {
      this.historyOpen = false;
      this.historySelected = null;
      this.historyDiff = '';
    }
  };
})(window.LaserPad);

window.laserPadApp = function laserPadApp() {
  const ns = window.LaserPad || {};
  return Object.assign(
    ns.state.createInitialState(),
    ns.selectors,
    ns.actions,
    ns.ui
  );
};

// ledsim-player.js — shared screen playback clock for Sim stage + Lab Room preview.
// AWR-266: one formula — Math.floor((ts - start) / 1000 * fps) mod frames.length
// (Lab preview loop). zoh/slew/latency are calibration MODEL knobs elsewhere; this
// module never applies them. Drawing stays in ledsim-view.js.

/**
 * Pure frame index from a performance timestamp (lab preview formula).
 * @param {number} ts
 * @param {number} start
 * @param {number} fps
 * @param {number} frameCount
 * @param {{loop?: boolean}} [opts]
 * @returns {{index: number, ended: boolean}}
 */
export function frameIndexAt(ts, start, fps, frameCount, opts = {}) {
  if (!frameCount || !(fps > 0) || !Number.isFinite(ts) || !Number.isFinite(start)) {
    return {index: 0, ended: false};
  }
  const raw = Math.floor((ts - start) / 1000 * fps);
  const loop = opts.loop !== false;
  if (loop) {
    const index = ((raw % frameCount) + frameCount) % frameCount;
    return {index, ended: false};
  }
  if (raw >= frameCount) return {index: frameCount - 1, ended: true};
  if (raw < 0) return {index: 0, ended: false};
  return {index: raw, ended: false};
}

/**
 * Wall-clock origin so that at `ts`, the given frame index is current.
 * Seek / scrub = adjust this offset (lab: start = ts - (frame / fps) * 1000).
 */
export function startOffsetForFrame(ts, frameIndex, fps) {
  const safeFps = fps > 0 ? fps : 40;
  return ts - (Math.max(0, Number(frameIndex) || 0) / safeFps) * 1000;
}

/**
 * @param {{
 *   onFrame: (frame: unknown, index: number, meta: {ts: number, ended: boolean}) => void,
 *   requestAnimationFrame?: typeof requestAnimationFrame,
 *   cancelAnimationFrame?: typeof cancelAnimationFrame,
 *   now?: () => number,
 * }} hooks
 */
export function createFramePlayer(hooks) {
  const raf = hooks.requestAnimationFrame || (
    typeof requestAnimationFrame === "function" ? requestAnimationFrame.bind(globalThis) : null
  );
  const caf = hooks.cancelAnimationFrame || (
    typeof cancelAnimationFrame === "function" ? cancelAnimationFrame.bind(globalThis) : null
  );
  const nowFn = hooks.now || (() => (
    typeof performance !== "undefined" && performance.now ? performance.now() : Date.now()
  ));
  if (typeof hooks.onFrame !== "function") {
    throw new Error("createFramePlayer requires onFrame");
  }

  let frames = [];
  let fps = 40;
  let loop = true;
  let playing = false;
  let start = undefined;
  let frozenIndex = 0;
  let handle = 0;

  function paint(ts, index, ended) {
    frozenIndex = index;
    const frame = frames[index];
    hooks.onFrame(frame, index, {ts, ended: Boolean(ended)});
  }

  function step(ts) {
    if (!playing || !frames.length) return;
    if (start === undefined) start = startOffsetForFrame(ts, frozenIndex, fps);
    const {index, ended} = frameIndexAt(ts, start, fps, frames.length, {loop});
    paint(ts, index, ended);
    if (ended) {
      playing = false;
      handle = 0;
      return;
    }
    handle = raf(step);
  }

  function stopRaf() {
    if (handle && caf) caf(handle);
    handle = 0;
  }

  return {
    setFrames(nextFrames, nextFps) {
      frames = Array.isArray(nextFrames) ? nextFrames : [];
      fps = Number(nextFps) > 0 ? Number(nextFps) : 40;
      if (frozenIndex >= frames.length) frozenIndex = Math.max(0, frames.length - 1);
    },
    setLoop(next) {
      loop = Boolean(next);
    },
    getLoop() {
      return loop;
    },
    getFps() {
      return fps;
    },
    getFrameCount() {
      return frames.length;
    },
    getIndex() {
      return frozenIndex;
    },
    isPlaying() {
      return playing;
    },
    /** Paint one frame without starting the clock (pause / scrub / boot). */
    show(index = frozenIndex) {
      if (!frames.length) return;
      frozenIndex = Math.max(0, Math.min(frames.length - 1, Number(index) || 0));
      paint(nowFn(), frozenIndex, false);
    },
    /**
     * Start (or restart) rAF playback.
     * @param {{fromFrame?: number}} [opts]
     */
    play(opts = {}) {
      if (!frames.length || !raf) return;
      stopRaf();
      const from = opts.fromFrame !== undefined ? opts.fromFrame : frozenIndex;
      frozenIndex = Math.max(0, Math.min(frames.length - 1, Number(from) || 0));
      playing = true;
      start = undefined; // seeded on first step from frozenIndex
      handle = raf(step);
    },
    /** Freeze on the current frame; scrub later resumes from that index. */
    pause() {
      if (!playing) return;
      playing = false;
      stopRaf();
      // Keep start so a mid-frame pause could resume — but scrub/seek is index-based;
      // next play() reseeds from frozenIndex (lab-equivalent clean freeze).
      start = undefined;
    },
    /**
     * Scrub to a frame. While playing, adjusts the start offset so motion continues
     * from that frame; while paused, paints and freezes there.
     */
    seek(index, ts = nowFn()) {
      if (!frames.length) return;
      frozenIndex = Math.max(0, Math.min(frames.length - 1, Number(index) || 0));
      if (playing) {
        start = startOffsetForFrame(ts, frozenIndex, fps);
      } else {
        start = undefined;
        paint(ts, frozenIndex, false);
      }
    },
    stop() {
      playing = false;
      stopRaf();
      start = undefined;
      frozenIndex = 0;
    },
    destroy() {
      this.stop();
      frames = [];
    },
  };
}

// ledsim-view.js — H612D fixture view. Draws only; never fetches or persists.

const H612D_SEGMENTS = 60;
const H612D_LEDS_PER_SEGMENT = 6;

export function createLedSimView(canvas, initialProfile) {
  const ctx = canvas.getContext("2d", {alpha: false});
  let profile = structuredClone(initialProfile || {});
  let lastFrame = [];
  let viewWidth = 1;
  let viewHeight = 1;
  let viewDpr = 1;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width || canvas.clientWidth || 800));
    const height = Math.max(1, Math.round(rect.height || canvas.clientHeight || 450));
    const dpr = Math.max(1, Number(window.devicePixelRatio) || 1);
    const backingWidth = Math.round(width * dpr);
    const backingHeight = Math.round(height * dpr);
    const backingChanged = canvas.width !== backingWidth || canvas.height !== backingHeight;
    const layoutChanged = backingChanged || width !== viewWidth || height !== viewHeight || dpr !== viewDpr;
    if (backingChanged) {
      canvas.width = backingWidth;
      canvas.height = backingHeight;
    }
    viewWidth = width;
    viewHeight = height;
    viewDpr = dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (layoutChanged) draw(lastFrame);
  }

  const resizeObserver = typeof ResizeObserver === "function" ? new ResizeObserver(resize) : null;
  if (resizeObserver) resizeObserver.observe(canvas);
  else window.addEventListener("resize", resize);

  function transformColor(rgb) {
    const gamma = Number(profile.gamma) || 1;
    const brightness = Number.isFinite(Number(profile.brightness)) ? Number(profile.brightness) : 1;
    const gains = profile.white_point || [1, 1, 1];
    return rgb.map((channel, index) => {
      const linear = (Number(gains[index]) || 0) * brightness * (Number(channel) / 255);
      return Math.max(0, Math.min(255, Math.round(255 * Math.max(0, linear) ** gamma)));
    });
  }

  // Mirror of led_sim_engine.apply_bleed: linear strip, no 59 -> 0 leak.
  function applyBleed(frame) {
    const mix = Number(profile.bleed) || 0;
    if (!frame.length || mix <= 0) return frame;
    return frame.map((current, index) => {
      const previous = index ? frame[index - 1] : current;
      const next = index + 1 < frame.length ? frame[index + 1] : current;
      return current.map((channel, c) => Math.max(0, Math.min(255, Math.round(
        (1 - mix) * channel + (mix / 2) * (previous[c] + next[c]),
      ))));
    });
  }

  function roundedRect(x, y, width, height, radius) {
    const r = Math.min(radius, width / 2, height / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + width, y, x + width, y + height, r);
    ctx.arcTo(x + width, y + height, x, y + height, r);
    ctx.arcTo(x, y + height, x, y, r);
    ctx.arcTo(x, y, x + width, y, r);
    ctx.closePath();
  }

  function drawEmitter(x, y, radius, rgb) {
    const [r, g, b] = rgb;
    const peak = Math.max(r, g, b) / 255;
    const glowRadius = radius * (2.2 + 2.8 * (Number(profile.glow_radius) || 1));
    const glowAlpha = Math.min(0.95, peak * (Number(profile.glow_gain) || 0));

    if (glowAlpha > 0.002) {
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      const glow = ctx.createRadialGradient(x, y, radius * 0.25, x, y, glowRadius);
      glow.addColorStop(0, `rgba(${r},${g},${b},${glowAlpha})`);
      glow.addColorStop(0.3, `rgba(${r},${g},${b},${glowAlpha * 0.42})`);
      glow.addColorStop(1, `rgba(${r},${g},${b},0)`);
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(x, y, glowRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    const core = ctx.createRadialGradient(
      x - radius * 0.25, y - radius * 0.28, radius * 0.08,
      x, y, radius,
    );
    const white = Math.round(peak * 210);
    core.addColorStop(0, `rgb(${Math.max(r, white)},${Math.max(g, white)},${Math.max(b, white)})`);
    core.addColorStop(0.34, `rgb(${r},${g},${b})`);
    core.addColorStop(1, `rgb(${Math.round(r * 0.14)},${Math.round(g * 0.14)},${Math.round(b * 0.14)})`);
    ctx.fillStyle = core;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = peak ? "rgba(255,255,255,.12)" : "rgba(255,255,255,.06)";
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  function invalidFrameReason(frame) {
    if (Number(profile.segments) !== H612D_SEGMENTS || Number(profile.leds_per_segment) !== H612D_LEDS_PER_SEGMENT) {
      return `profile must be ${H612D_SEGMENTS} segments × ${H612D_LEDS_PER_SEGMENT} LEDs`;
    }
    if (!Array.isArray(frame) || frame.length !== H612D_SEGMENTS) {
      return `expected ${H612D_SEGMENTS} RGB segments, received ${Array.isArray(frame) ? frame.length : "non-array"}`;
    }
    const badPixel = frame.findIndex((pixel) => (
      !Array.isArray(pixel)
      || pixel.length !== 3
      || pixel.some((channel) => !Number.isFinite(Number(channel)) || Number(channel) < 0 || Number(channel) > 255)
    ));
    return badPixel < 0 ? "" : `segment ${badPixel} is not a valid RGB triplet`;
  }

  function drawInvalid(reason) {
    ctx.fillStyle = "#19070c";
    ctx.fillRect(0, 0, viewWidth, viewHeight);
    ctx.strokeStyle = "#ff496c";
    ctx.lineWidth = 3;
    ctx.strokeRect(20, 20, Math.max(1, viewWidth - 40), Math.max(1, viewHeight - 40));
    ctx.fillStyle = "#ff7690";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "800 18px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.fillText("INVALID H612D FRAME", viewWidth / 2, viewHeight / 2 - 16);
    ctx.fillStyle = "#ffc1cc";
    ctx.font = "600 12px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.fillText(reason, viewWidth / 2, viewHeight / 2 + 18);
  }

  function draw(frame) {
    const width = viewWidth;
    const height = viewHeight;
    const invalid = invalidFrameReason(frame);
    if (invalid) {
      drawInvalid(invalid);
      return;
    }
    const segments = H612D_SEGMENTS;
    const ledsPerSegment = H612D_LEDS_PER_SEGMENT;
    const segmentsPerRow = 10;
    const rows = Math.ceil(segments / segmentsPerRow);
    const padX = 54;
    const padTop = 46;
    const padBottom = 38;
    const usableWidth = width - padX * 2;
    const rowHeight = (height - padTop - padBottom) / rows;
    const segmentWidth = usableWidth / segmentsPerRow;
    const emitterRadius = Math.max(3.2, Math.min(7.5, segmentWidth / (ledsPerSegment * 3.2)));

    const backdrop = ctx.createLinearGradient(0, 0, 0, height);
    backdrop.addColorStop(0, "#080912");
    backdrop.addColorStop(1, "#030408");
    ctx.fillStyle = backdrop;
    ctx.fillRect(0, 0, width, height);

    const transformed = applyBleed(frame.map(transformColor));

    ctx.font = "600 11px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.textBaseline = "middle";
    for (let row = 0; row < rows; row += 1) {
      const y = padTop + row * rowHeight + rowHeight * 0.45;
      const first = row * segmentsPerRow;
      const last = Math.min(segments, first + segmentsPerRow);

      ctx.fillStyle = "#11131b";
      roundedRect(padX - 12, y - 17, usableWidth + 24, 34, 10);
      ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,.06)";
      ctx.stroke();

      for (let segment = first; segment < last; segment += 1) {
        const column = segment - first;
        const segmentX = padX + column * segmentWidth;
        const rgb = transformed[segment];

        if (column) {
          ctx.strokeStyle = "rgba(255,255,255,.075)";
          ctx.beginPath();
          ctx.moveTo(segmentX, y - 13);
          ctx.lineTo(segmentX, y + 13);
          ctx.stroke();
        }

        for (let led = 0; led < ledsPerSegment; led += 1) {
          const x = segmentX + ((led + 0.5) / ledsPerSegment) * segmentWidth;
          drawEmitter(x, y, emitterRadius, rgb);
        }

        ctx.fillStyle = "rgba(195,202,220,.48)";
        ctx.textAlign = "center";
        ctx.fillText(String(segment).padStart(2, "0"), segmentX + segmentWidth / 2, y + 31);
      }

      ctx.fillStyle = "rgba(137,146,170,.62)";
      ctx.textAlign = "right";
      ctx.fillText(`${String(first).padStart(2, "0")}–${String(last - 1).padStart(2, "0")}`, padX - 18, y);
    }
  }

  const api = {
    renderFrame(frame) {
      lastFrame = frame || [];
      draw(lastFrame);
    },
    setProfile(next) {
      profile = structuredClone(next || {});
      draw(lastFrame);
    },
    destroy() {
      if (resizeObserver) resizeObserver.disconnect();
      else window.removeEventListener("resize", resize);
      lastFrame = [];
      ctx.clearRect(0, 0, viewWidth, viewHeight);
    },
  };

  resize();
  return api;
}

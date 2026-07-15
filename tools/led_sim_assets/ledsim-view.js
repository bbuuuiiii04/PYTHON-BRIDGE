// ledsim-view.js — H612D fixture view. Draws only; never fetches or persists.
// Layout math mirrors tools/led_sim_engine.py — keep in lockstep.

const H612D_SEGMENTS = 60;
const H612D_LEDS_PER_SEGMENT = 6;
const H612D_PHYSICAL_LEDS = 360;
const H612D_LENGTH_MM = 14996.16;
const H612D_JUNCTION_MM = H612D_LENGTH_MM / 2; // 7498.08 absolute arc mm
const H612D_LED_PITCH_MM = H612D_LENGTH_MM / H612D_PHYSICAL_LEDS; // 41.656
const H612D_SEGMENT_MM = H612D_LENGTH_MM / H612D_SEGMENTS;
const MM_PER_FOOT = 304.8;
const DEFAULT_ROOM_MM = [5216, 2284];

function roomSizeMm(profile) {
  const room = profile?.room_mm;
  if (
    Array.isArray(room)
    && room.length === 2
    && room.every((value) => Number.isFinite(Number(value)) && Number(value) > 0)
  ) {
    return [Number(room[0]), Number(room[1])];
  }
  return [...DEFAULT_ROOM_MM];
}

export function formatLengthMm(mm) {
  const feet = Number(mm) / MM_PER_FOOT;
  const meters = Number(mm) / 1000;
  return `${feet.toFixed(1)} ft · ${meters.toFixed(1)} m`;
}

export function mmToFeet(mm) {
  return Number(mm) / MM_PER_FOOT;
}

export function feetToMm(feet) {
  return Number(feet) * MM_PER_FOOT;
}

export function perimeterPresetPoints(roomMm) {
  const [width, height] = roomMm && roomMm.length === 2 ? roomMm.map(Number) : DEFAULT_ROOM_MM;
  const perimeter = 2 * (width + height);
  let gap = perimeter - H612D_LENGTH_MM;
  if (gap < 0) gap = Math.min(width * 0.001, 1);
  // Gap wider than the bottom wall → U-path corner to corner (never outside room).
  if (gap > width) {
    return [
      [0, 0],
      [0, height],
      [width, height],
      [width, 0],
    ];
  }
  const half = width / 2;
  return [
    [half - gap / 2, 0],
    [0, 0],
    [0, height],
    [half, height],
    [width, height],
    [width, 0],
    [half + gap / 2, 0],
  ];
}

export function snakePresetPoints(roomMm) {
  // Big S: exactly 3 horizontal runs + 2 vertical connectors (mirrors engine).
  const [width, height] = roomMm && roomMm.length === 2 ? roomMm.map(Number) : DEFAULT_ROOM_MM;
  const strip = H612D_LENGTH_MM;
  const margin = Math.min(200, Math.min(width, height) * 0.05);
  const availW = Math.max(1, width - 2 * margin);
  const availH = Math.max(1, height - 2 * margin);
  let connector = availH / 2;
  let run = (strip - 2 * connector) / 3;
  if (run > availW) {
    run = availW;
    connector = (strip - 3 * run) / 2;
  }
  if (run <= 0) {
    run = Math.min(availW, strip / 3);
    connector = Math.max(0, (strip - 3 * run) / 2);
  }
  if (connector < 0) {
    connector = 0;
    run = strip / 3;
  }
  let left = margin + Math.max(0, (availW - run) / 2);
  let right = left + run;
  let y0;
  if (2 * connector <= availH + 1e-9) {
    y0 = margin + (availH - 2 * connector) / 2;
  } else {
    y0 = margin;
    connector = availH / 2;
    run = (strip - 2 * connector) / 3;
    left = margin + Math.max(0, (availW - run) / 2);
    right = left + run;
  }
  const y1 = y0 + connector;
  const y2 = y1 + connector;
  return [
    [left, y0],
    [right, y0],
    [right, y1],
    [left, y1],
    [left, y2],
    [right, y2],
  ];
}

export function defaultLayout(roomMm) {
  return {
    preset: "perimeter",
    points_mm: perimeterPresetPoints(roomMm),
    flip_chain: false,
  };
}

export function resolveLayout(profile) {
  const room = roomSizeMm(profile);
  const layout = profile?.layout;
  if (!layout || typeof layout !== "object") return defaultLayout(room);
  let preset = layout.preset || "custom";
  if (!["perimeter", "snake", "custom"].includes(preset)) preset = "custom";
  let points = layout.points_mm;
  if ((preset === "perimeter" || preset === "snake") && (!Array.isArray(points) || points.length < 2)) {
    points = preset === "snake" ? snakePresetPoints(room) : perimeterPresetPoints(room);
  } else if (!Array.isArray(points) || points.length < 2) {
    points = perimeterPresetPoints(room);
    preset = "perimeter";
  }
  return {
    preset,
    points_mm: points.map((point) => [Number(point[0]), Number(point[1])]),
    // Strict boolean — mirror engine resolve_layout (non-bool → False).
    flip_chain: typeof layout.flip_chain === "boolean" ? layout.flip_chain : false,
  };
}

function polylineArcLength(points) {
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const [x0, y0] = points[index - 1];
    const [x1, y1] = points[index];
    total += Math.hypot(x1 - x0, y1 - y0);
  }
  return total;
}

function pointAtArcDistance(points, distance, totalLength) {
  if (!points.length) return [0, 0];
  if (points.length === 1 || totalLength <= 0) return [points[0][0], points[0][1]];
  const target = Math.max(0, Math.min(distance, totalLength));
  if (target >= totalLength) {
    const last = points[points.length - 1];
    return [last[0], last[1]];
  }
  let walked = 0;
  for (let index = 1; index < points.length; index += 1) {
    const [x0, y0] = points[index - 1];
    const [x1, y1] = points[index];
    const edge = Math.hypot(x1 - x0, y1 - y0);
    if (edge <= 1e-12) continue;
    if (walked + edge >= target) {
      const t = (target - walked) / edge;
      return [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t];
    }
    walked += edge;
  }
  const last = points[points.length - 1];
  return [last[0], last[1]];
}

// Mirror of led_sim_engine.layout_led_positions — keep in lockstep.
export function layoutLedPositions(profile) {
  const layout = resolveLayout(profile);
  let points = layout.points_mm.map((point) => [point[0], point[1]]);
  if (layout.flip_chain) points = points.slice().reverse();
  const pathLength = polylineArcLength(points);
  const stripLength = H612D_LENGTH_MM;
  const pitch = H612D_LED_PITCH_MM;
  const segmentMm = H612D_SEGMENT_MM;
  const placedLength = Math.min(pathLength, stripLength);
  let unplacedMm = Math.max(0, stripLength - pathLength);
  let excessPathMm = Math.max(0, pathLength - stripLength);
  if (excessPathMm < 1e-6) excessPathMm = 0;
  if (unplacedMm < 1e-6) unplacedMm = 0;

  function sample(arcMm) {
    if (pathLength <= 1e-12) return points[0] ? [points[0][0], points[0][1]] : [0, 0];
    return pointAtArcDistance(points, Math.min(Math.max(0, arcMm), pathLength), pathLength);
  }

  const ledPositions = [];
  for (let index = 0; index < H612D_PHYSICAL_LEDS; index += 1) {
    const distance = (index + 0.5) * pitch;
    ledPositions.push(distance <= pathLength + 1e-9 ? sample(distance) : null);
  }
  const boundaries = [];
  for (let index = 0; index <= H612D_SEGMENTS; index += 1) {
    const distance = index * segmentMm;
    boundaries.push(distance <= pathLength + 1e-9 ? sample(distance) : null);
  }
  return {
    leds_mm: ledPositions,
    segment_boundaries_mm: boundaries,
    junction_mm: pathLength + 1e-9 >= H612D_JUNCTION_MM ? sample(H612D_JUNCTION_MM) : null,
    start_mm: sample(0),
    end_mm: sample(placedLength),
    path_end_mm: sample(pathLength),
    points_mm: points,
    path_length_mm: pathLength,
    strip_length_mm: stripLength,
    placed_length_mm: placedLength,
    unplaced_mm: unplacedMm,
    excess_path_mm: excessPathMm,
    led_pitch_mm: pitch,
    segment_mm: segmentMm,
    junction_arc_mm: H612D_JUNCTION_MM,
    flip_chain: Boolean(layout.flip_chain),
    preset: layout.preset,
    path_label: formatLengthMm(pathLength),
    strip_label: formatLengthMm(stripLength),
  };
}

export function createLedSimView(canvas, initialProfile) {
  const ctx = canvas.getContext("2d", {alpha: false});
  let profile = structuredClone(initialProfile || {});
  let lastFrame = [];
  let viewWidth = 1;
  let viewHeight = 1;
  let viewDpr = 1;
  let viewMode = "room";
  let labelsVisible = typeof window !== "undefined" ? window.innerWidth >= 700 : true;
  let editing = false;
  let layoutCache = null;
  let screenCache = null;

  function invalidateLayout() {
    layoutCache = null;
    screenCache = null;
  }

  function ensureLayout() {
    if (!layoutCache) layoutCache = layoutLedPositions(profile);
    return layoutCache;
  }

  function roomTransform() {
    const [roomW, roomH] = roomSizeMm(profile);
    const pad = Math.min(viewWidth, viewHeight) * 0.08;
    const availW = Math.max(1, viewWidth - pad * 2);
    const availH = Math.max(1, viewHeight - pad * 2);
    const scale = Math.min(availW / roomW, availH / roomH);
    const drawW = roomW * scale;
    const drawH = roomH * scale;
    const originX = (viewWidth - drawW) / 2;
    const originY = (viewHeight - drawH) / 2;
    return {roomW, roomH, scale, originX, originY, drawW, drawH, pad};
  }

  function mmToCanvas(xMm, yMm, transform = roomTransform()) {
    // Room y=0 is the bottom edge; canvas y grows downward.
    return {
      x: transform.originX + xMm * transform.scale,
      y: transform.originY + (transform.roomH - yMm) * transform.scale,
    };
  }

  function canvasToMm(canvasX, canvasY, transform = roomTransform()) {
    return {
      x: (canvasX - transform.originX) / transform.scale,
      y: transform.roomH - (canvasY - transform.originY) / transform.scale,
    };
  }

  function ensureScreenCache() {
    const layout = ensureLayout();
    const transform = roomTransform();
    const key = [
      viewWidth, viewHeight, viewDpr, viewMode,
      transform.scale, transform.originX, transform.originY,
      layout.path_length_mm, layout.flip_chain, layout.points_mm.length,
      layout.unplaced_mm, layout.excess_path_mm,
    ].join("|");
    if (screenCache && screenCache.key === key) return screenCache;

    const toScreen = (point) => (point ? mmToCanvas(point[0], point[1], transform) : null);
    const leds = layout.leds_mm.map(toScreen);
    const points = layout.points_mm.map(([x, y]) => mmToCanvas(x, y, transform));
    const boundaries = layout.segment_boundaries_mm.map(toScreen);
    const junction = toScreen(layout.junction_mm);
    const start = toScreen(layout.start_mm);
    const end = toScreen(layout.end_mm);
    const pathEnd = toScreen(layout.path_end_mm);
    screenCache = {key, transform, leds, points, boundaries, junction, start, end, pathEnd, layout};
    return screenCache;
  }

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
    if (layoutChanged) {
      screenCache = null;
      draw(lastFrame);
    }
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
    ctx.arcTo(x + width, y + height, x, y, r);
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

  function drawStripBench(transformed) {
    const width = viewWidth;
    const height = viewHeight;
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

        if (labelsVisible) {
          ctx.fillStyle = "rgba(195,202,220,.48)";
          ctx.textAlign = "center";
          ctx.fillText(String(segment).padStart(2, "0"), segmentX + segmentWidth / 2, y + 31);
        }
      }

      if (labelsVisible) {
        ctx.fillStyle = "rgba(137,146,170,.62)";
        ctx.textAlign = "right";
        ctx.fillText(`${String(first).padStart(2, "0")}–${String(last - 1).padStart(2, "0")}`, padX - 18, y);
      }
    }
  }

  function drawControlBox(x, y) {
    const w = 14;
    const h = 10;
    ctx.fillStyle = "#1c2233";
    ctx.strokeStyle = "#8a6cff";
    ctx.lineWidth = 1.5;
    roundedRect(x - w / 2, y - h / 2, w, h, 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#5ce1e6";
    ctx.fillRect(x - 3, y - 1.5, 6, 3);
  }

  function drawRoom(transformed) {
    const width = viewWidth;
    const height = viewHeight;
    const screen = ensureScreenCache();
    const {transform, leds, points, boundaries, junction, start, end, pathEnd, layout} = screen;
    const roomCx = transform.originX + transform.drawW / 2;
    const roomCy = transform.originY + transform.drawH / 2;

    const backdrop = ctx.createLinearGradient(0, 0, 0, height);
    backdrop.addColorStop(0, "#0a0c14");
    backdrop.addColorStop(1, "#04050a");
    ctx.fillStyle = backdrop;
    ctx.fillRect(0, 0, width, height);

    // Flat room floor + clear wall rectangle (never reuse the strip path for fill).
    ctx.beginPath();
    ctx.fillStyle = "rgba(16, 20, 32, .95)";
    ctx.fillRect(transform.originX, transform.originY, transform.drawW, transform.drawH);
    ctx.strokeStyle = "rgba(200, 210, 230, .28)";
    ctx.lineWidth = 1;
    ctx.setLineDash([]);
    ctx.strokeRect(transform.originX + 0.5, transform.originY + 0.5, transform.drawW - 1, transform.drawH - 1);
    ctx.beginPath();

    // Strip path — stroke only; always beginPath afterward so nothing can fill it.
    if (points.length >= 2) {
      const stripEndArc = layout.placed_length_mm;
      ctx.strokeStyle = "rgba(138,108,255,.4)";
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.setLineDash([]);
      ctx.beginPath();
      let walked = 0;
      let started = false;
      for (let index = 1; index < layout.points_mm.length; index += 1) {
        const a = layout.points_mm[index - 1];
        const b = layout.points_mm[index];
        const edge = Math.hypot(b[0] - a[0], b[1] - a[1]);
        if (edge <= 1e-12) continue;
        const from = walked;
        const to = walked + edge;
        if (to <= stripEndArc + 1e-9) {
          const sa = mmToCanvas(a[0], a[1], transform);
          const sb = mmToCanvas(b[0], b[1], transform);
          if (!started) {
            ctx.moveTo(sa.x, sa.y);
            started = true;
          }
          ctx.lineTo(sb.x, sb.y);
        } else if (from < stripEndArc) {
          const t = (stripEndArc - from) / edge;
          const mx = a[0] + (b[0] - a[0]) * t;
          const my = a[1] + (b[1] - a[1]) * t;
          const sa = mmToCanvas(a[0], a[1], transform);
          const sm = mmToCanvas(mx, my, transform);
          if (!started) {
            ctx.moveTo(sa.x, sa.y);
            started = true;
          }
          ctx.lineTo(sm.x, sm.y);
        }
        walked = to;
      }
      if (started) ctx.stroke();
      ctx.beginPath();

      if (layout.excess_path_mm > 0 && end && pathEnd) {
        ctx.strokeStyle = "rgba(138,108,255,.22)";
        ctx.setLineDash([6, 5]);
        ctx.beginPath();
        walked = 0;
        started = false;
        for (let index = 1; index < layout.points_mm.length; index += 1) {
          const a = layout.points_mm[index - 1];
          const b = layout.points_mm[index];
          const edge = Math.hypot(b[0] - a[0], b[1] - a[1]);
          if (edge <= 1e-12) continue;
          const from = walked;
          const to = walked + edge;
          if (to <= stripEndArc + 1e-9) {
            walked = to;
            continue;
          }
          const startT = from >= stripEndArc ? 0 : (stripEndArc - from) / edge;
          const x0 = a[0] + (b[0] - a[0]) * startT;
          const y0 = a[1] + (b[1] - a[1]) * startT;
          const s0 = mmToCanvas(x0, y0, transform);
          const s1 = mmToCanvas(b[0], b[1], transform);
          if (!started) {
            ctx.moveTo(s0.x, s0.y);
            started = true;
          } else {
            ctx.lineTo(s0.x, s0.y);
          }
          ctx.lineTo(s1.x, s1.y);
          walked = to;
        }
        if (started) ctx.stroke();
        ctx.setLineDash([]);
        ctx.beginPath();
      }
    }

    const emitterRadius = Math.max(2.4, Math.min(5.5, transform.scale * 18));
    for (let led = 0; led < leds.length; led += 1) {
      if (!leds[led]) continue;
      const segment = Math.floor(led / H612D_LEDS_PER_SEGMENT);
      drawEmitter(leds[led].x, leds[led].y, emitterRadius, transformed[segment]);
    }
    ctx.beginPath();

    if (start) {
      ctx.fillStyle = "#7ee0b6";
      ctx.beginPath();
      ctx.arc(start.x, start.y, 5, 0, Math.PI * 2);
      ctx.fill();
    }
    if (end) {
      ctx.fillStyle = "#ff7690";
      ctx.beginPath();
      ctx.arc(end.x, end.y, 5, 0, Math.PI * 2);
      ctx.fill();
    }
    if (junction) drawControlBox(junction.x, junction.y);
    ctx.beginPath();

    if (labelsVisible) {
      drawRoomLabels({
        layout, transform, boundaries, junction, start, end, roomCx, roomCy,
      });
    }

    if (layout.unplaced_mm > 0) {
      ctx.beginPath();
      ctx.fillStyle = "rgba(255, 193, 92, .95)";
      ctx.font = "700 12px ui-sans-serif, -apple-system, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(
        `Path ${layout.path_label} / Strip ${layout.strip_label} — ${formatLengthMm(layout.unplaced_mm)} unplaced`,
        transform.originX + 10,
        transform.originY + 10,
      );
      if (end) {
        ctx.strokeStyle = "#ffc15c";
        ctx.lineWidth = 2;
        ctx.strokeRect(end.x - 8, end.y - 8, 16, 16);
      }
      ctx.beginPath();
    }

    if (editing) {
      const handleR = 6;
      for (const point of points) {
        ctx.fillStyle = "#f2f4fb";
        ctx.strokeStyle = "#8a6cff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(point.x, point.y, handleR, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
      ctx.beginPath();
    }
  }

  function pathTangentAt(layout, arcMm) {
    const pts = layout.points_mm;
    let walked = 0;
    for (let index = 1; index < pts.length; index += 1) {
      const a = pts[index - 1];
      const b = pts[index];
      const edge = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (edge <= 1e-12) continue;
      if (walked + edge >= arcMm - 1e-9) {
        return {dx: (b[0] - a[0]) / edge, dy: (b[1] - a[1]) / edge};
      }
      walked += edge;
    }
    if (pts.length >= 2) {
      const a = pts[pts.length - 2];
      const b = pts[pts.length - 1];
      const edge = Math.max(1e-9, Math.hypot(b[0] - a[0], b[1] - a[1]));
      return {dx: (b[0] - a[0]) / edge, dy: (b[1] - a[1]) / edge};
    }
    return {dx: 1, dy: 0};
  }

  function outwardNormal(tangent, screenPoint, roomCx, roomCy) {
    // Perpendicular; pick the direction pointing away from room center.
    let nx = -tangent.dy;
    let ny = tangent.dx;
    const len = Math.hypot(nx, ny) || 1;
    nx /= len;
    ny /= len;
    const toCenterX = roomCx - screenPoint.x;
    const toCenterY = roomCy - screenPoint.y;
    if (nx * toCenterX + ny * toCenterY > 0) {
      nx = -nx;
      ny = -ny;
    }
    return {nx, ny};
  }

  function boxesOverlap(a, b, pad = 3) {
    return !(
      a.x + a.w + pad < b.x
      || b.x + b.w + pad < a.x
      || a.y + a.h + pad < b.y
      || b.y + b.h + pad < a.y
    );
  }

  function drawRoomLabels({layout, transform, boundaries, junction, start, end, roomCx, roomCy}) {
    const placed = [];
    const font = "700 11px ui-sans-serif, -apple-system, sans-serif";
    const tickFont = "600 10px ui-monospace, SFMono-Regular, Menlo, monospace";

    function measure(text, useFont) {
      ctx.font = useFont;
      const metrics = ctx.measureText(text);
      const w = metrics.width;
      const h = 12;
      return {w, h};
    }

    function tryDraw(text, anchor, arcMm, options = {}) {
      const useFont = options.font || font;
      const size = measure(text, useFont);
      const tangent = pathTangentAt(layout, arcMm);
      // mm y-up → screen y-down: flip tangent dy for screen-space normals.
      const screenTangent = {dx: tangent.dx, dy: -tangent.dy};
      let screenNormal = outwardNormal(screenTangent, anchor, roomCx, roomCy);
      const offset = options.offset ?? 14;
      const stack = options.stack || 0;
      const pad = 6;

      function placeWithNormal(normal) {
        let x = anchor.x + normal.nx * offset;
        let y = anchor.y + normal.ny * offset + stack;
        if (options.align === "center") {
          x -= size.w / 2;
          y -= size.h / 2;
        } else if (normal.nx < 0) {
          x -= size.w;
        }
        return {x, y, w: size.w, h: size.h};
      }

      let box = placeWithNormal(screenNormal);
      // Prefer flipping inward over clipping at the canvas edge.
      const wouldClip = (
        box.x < pad
        || box.y < pad
        || box.x + box.w > viewWidth - pad
        || box.y + box.h > viewHeight - pad
      );
      if (wouldClip) {
        const inward = {nx: -screenNormal.nx, ny: -screenNormal.ny};
        const flipped = placeWithNormal(inward);
        const flippedClips = (
          flipped.x < pad
          || flipped.y < pad
          || flipped.x + flipped.w > viewWidth - pad
          || flipped.y + flipped.h > viewHeight - pad
        );
        if (!flippedClips || (
          Math.min(flipped.x, viewWidth - (flipped.x + flipped.w))
          > Math.min(box.x, viewWidth - (box.x + box.w))
        )) {
          box = flipped;
          screenNormal = inward;
        }
      }
      box.x = Math.max(pad, Math.min(viewWidth - box.w - pad, box.x));
      box.y = Math.max(pad, Math.min(viewHeight - box.h - pad, box.y));
      if (placed.some((other) => boxesOverlap(box, other))) return false;
      placed.push(box);
      ctx.font = useFont;
      ctx.fillStyle = options.color || "#4dd8e6";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(text, box.x, box.y);
      return true;
    }

    // Priority: center > start > end > ticks
    if (junction) {
      tryDraw("center · control box · 24.6 ft", junction, H612D_JUNCTION_MM, {
        color: "#4dd8e6", offset: 16,
      });
    }

    // Start/end near the same gap: stack vertically when close.
    const gapClose = start && end && Math.hypot(start.x - end.x, start.y - end.y) < 40;
    if (start) {
      tryDraw("start", start, 0, {
        color: "#3fd68f",
        offset: 14,
        stack: gapClose ? -10 : 0,
      });
    }
    if (end) {
      tryDraw(`end · ${formatLengthMm(layout.placed_length_mm)}`, end, layout.placed_length_mm, {
        color: "#f25f5c",
        offset: 14,
        stack: gapClose ? 10 : 0,
      });
    }

    for (let segment = 0; segment < H612D_SEGMENTS; segment += 10) {
      // AF-4: suppress the tick that coincides with the junction glyph (seg 30).
      if (Math.abs(segment * H612D_SEGMENT_MM - H612D_JUNCTION_MM) < 1e-6) continue;
      const point = boundaries[segment];
      if (!point) continue;
      ctx.beginPath();
      ctx.strokeStyle = "rgba(195,202,220,.35)";
      ctx.lineWidth = 1;
      ctx.moveTo(point.x, point.y - 5);
      ctx.lineTo(point.x, point.y + 5);
      ctx.stroke();
      ctx.beginPath();
      const label = `${String(segment).padStart(2, "0")} · ${formatLengthMm(segment * H612D_SEGMENT_MM)}`;
      tryDraw(label, point, segment * H612D_SEGMENT_MM, {
        color: "rgba(195,202,220,.85)",
        font: tickFont,
        offset: 12,
      });
    }
  }

  function draw(frame) {
    const invalid = invalidFrameReason(frame);
    if (invalid) {
      drawInvalid(invalid);
      return;
    }
    const transformed = applyBleed(frame.map(transformColor));
    if (viewMode === "strip") drawStripBench(transformed);
    else drawRoom(transformed);
  }

  function hitTestVertex(canvasX, canvasY, thresholdPx = 16) {
    const screen = ensureScreenCache();
    let best = -1;
    let bestDist = thresholdPx;
    screen.points.forEach((point, index) => {
      const dist = Math.hypot(point.x - canvasX, point.y - canvasY);
      if (dist <= bestDist) {
        bestDist = dist;
        best = index;
      }
    });
    return best;
  }

  function hitTestEdge(canvasX, canvasY, thresholdPx = 14) {
    const screen = ensureScreenCache();
    const points = screen.points;
    let best = -1;
    let bestDist = thresholdPx;
    let bestT = 0.5;
    for (let index = 0; index < points.length - 1; index += 1) {
      const a = points[index];
      const b = points[index + 1];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const len2 = dx * dx + dy * dy;
      if (len2 < 1e-6) continue;
      let t = ((canvasX - a.x) * dx + (canvasY - a.y) * dy) / len2;
      t = Math.max(0.05, Math.min(0.95, t));
      const px = a.x + dx * t;
      const py = a.y + dy * t;
      const dist = Math.hypot(px - canvasX, py - canvasY);
      if (dist <= bestDist) {
        bestDist = dist;
        best = index;
        bestT = t;
      }
    }
    if (best < 0) return null;
    const mm = canvasToMm(
      points[best].x + (points[best + 1].x - points[best].x) * bestT,
      points[best].y + (points[best + 1].y - points[best].y) * bestT,
      screen.transform,
    );
    return {edgeIndex: best, t: bestT, mm};
  }

  const api = {
    renderFrame(frame) {
      lastFrame = frame || [];
      draw(lastFrame);
    },
    setProfile(next) {
      profile = structuredClone(next || {});
      invalidateLayout();
      draw(lastFrame);
    },
    setViewMode(mode) {
      viewMode = mode === "strip" ? "strip" : "room";
      screenCache = null;
      draw(lastFrame);
    },
    getViewMode() {
      return viewMode;
    },
    setLabelsVisible(visible) {
      labelsVisible = Boolean(visible);
      draw(lastFrame);
    },
    getLabelsVisible() {
      return labelsVisible;
    },
    setEditing(next) {
      editing = Boolean(next);
      draw(lastFrame);
    },
    mmToCanvas(xMm, yMm) {
      return mmToCanvas(xMm, yMm);
    },
    canvasToMm(canvasX, canvasY) {
      return canvasToMm(canvasX, canvasY);
    },
    hitTestVertex,
    hitTestEdge,
    getLayout() {
      return ensureLayout();
    },
    invalidateLayout() {
      invalidateLayout();
      draw(lastFrame);
    },
    redraw() {
      draw(lastFrame);
    },
    destroy() {
      if (resizeObserver) resizeObserver.disconnect();
      else window.removeEventListener("resize", resize);
      lastFrame = [];
      invalidateLayout();
      ctx.clearRect(0, 0, viewWidth, viewHeight);
    },
  };

  resize();
  return api;
}

// ledsim-view.js — LED room simulator view (AWR-196). THE SWAPPABLE SEAM.
//
// SEAM CONTRACT (read this before the future pad-round integration):
//   import { createLedSimView } from "./ledsim-view.js";
//   const view = createLedSimView(canvas, profile);
//   view.renderFrame(frame);  // frame = [[r,g,b] × segments], RAW renderer output
//   view.setProfile(p);       // geometry + photometric knobs; `_calibrating`
//                             // (truthy) shows the drag affordances
//   view.hitTest(x, y);       // canvas px -> {type:"corner"|"start"|"direction",
//                             //   index?, tangent?, segPerPx?} or null
//   view.destroy();
// This module is self-contained (no imports). It DRAWS ONLY: it never fetches,
// persists, or edits the profile. A host mounts it and feeds frames — nothing
// else. hitTest hands the host enough geometry (travel tangent + segments-per-
// pixel) to wire its own dragging; all profile edits stay host-owned.
//
// The photometric/bleed/geometry formulas here are DELIBERATE mirrors of the
// Python engine (interactive knobs must not round-trip the server per slider
// tick). The Python twins carry the unit tests; keep each mirror in lockstep.

export function createLedSimView(canvas, initialProfile) {
  const ctx = canvas.getContext("2d");
  let profile = JSON.parse(JSON.stringify(initialProfile || {}));
  let lastFrame = null;
  let directionHitCenter = null; // set during overlay draw, canvas px

  // --- geometry -------------------------------------------------------------
  // mirror of led_sim_engine.segment_geometry — keep in lockstep
  function roomCorners() {
    const room = profile.room_mm || [5216, 2284];
    const w = Number(room[0]) || 1;
    const h = Number(room[1]) || 1;
    return [[0, 0], [w, 0], [w, h], [0, h]]; // clockwise, y down
  }

  const INWARD_NORMALS = [[0, 1], [-1, 0], [0, -1], [1, 0]]; // physical wall 0-3

  function traversedWalls() {
    const corners = roomCorners();
    const start = (Number(profile.start_corner) || 0) & 3;
    const cw = profile.direction !== "ccw";
    const walls = [];
    for (let k = 0; k < 4; k += 1) {
      let a, b, wallIndex;
      if (cw) {
        a = (start + k) % 4;
        b = (a + 1) % 4;
        wallIndex = a;
      } else {
        a = ((start - k) % 4 + 4) % 4;
        b = ((a - 1) % 4 + 4) % 4;
        wallIndex = b; // physical wall j connects corner j -> j+1
      }
      walls.push({ a: corners[a], b: corners[b], wallIndex });
    }
    return walls;
  }

  function arcLengths() {
    const seg = Number(profile.segments) || 60;
    const cs = profile.corner_segments || [0, 15, 30, 45];
    const out = [];
    for (let k = 0; k < 4; k += 1) {
      out.push(k < 3 ? cs[k + 1] - cs[k] : seg - cs[3] + cs[0]);
    }
    return out;
  }

  // strip position (0..segments) -> {x, y, wallIndex, tangent} in room mm
  function stripPosToPoint(pos) {
    const seg = Number(profile.segments) || 60;
    const cs = profile.corner_segments || [0, 15, 30, 45];
    const walls = traversedWalls();
    const arcs = arcLengths();
    let rel = ((pos - cs[0]) % seg + seg) % seg;
    let offset = 0;
    for (let k = 0; k < 4; k += 1) {
      if (rel < offset + arcs[k] || k === 3) {
        const frac = (rel - offset) / arcs[k];
        const [ax, ay] = walls[k].a;
        const [bx, by] = walls[k].b;
        const dx = bx - ax;
        const dy = by - ay;
        const len = Math.hypot(dx, dy) || 1;
        return {
          x: ax + dx * frac,
          y: ay + dy * frac,
          wallIndex: walls[k].wallIndex,
          tangent: [dx / len, dy / len],
        };
      }
      offset += arcs[k];
    }
    return { x: 0, y: 0, wallIndex: 0, tangent: [1, 0] };
  }

  // --- canvas fit -------------------------------------------------------------
  const MARGIN = 56;

  function fit() {
    const room = roomCorners();
    const w = room[1][0];
    const h = room[3][1];
    const cw = canvas.width;
    const ch = canvas.height;
    const scale = Math.min((cw - 2 * MARGIN) / w, (ch - 2 * MARGIN) / h);
    const ox = (cw - w * scale) / 2;
    const oy = (ch - h * scale) / 2;
    return { scale, ox, oy, w, h };
  }

  function toCanvas(f, x, y) {
    return [f.ox + x * f.scale, f.oy + y * f.scale];
  }

  // --- photometrics -------------------------------------------------------------
  // mirror of led_sim_engine formula: out_c = 255*(gain_c*brightness*(in_c/255))^gamma
  // — keep in lockstep
  function transformColor(rgb) {
    const gamma = Number(profile.gamma) || 1.0;
    const brightness = Number(profile.brightness);
    const bright = Number.isFinite(brightness) ? brightness : 1.0;
    const white = profile.white_point || [1, 1, 1];
    const out = [0, 0, 0];
    for (let c = 0; c < 3; c += 1) {
      const linear = (Number(white[c]) || 0) * bright * (rgb[c] / 255);
      out[c] = Math.max(0, Math.min(255, Math.round(255 * Math.pow(Math.max(0, linear), gamma))));
    }
    return out;
  }

  // mirror of led_sim_engine.apply_bleed — keep in lockstep
  function applyBleed(frame, bleed) {
    const n = frame.length;
    const mix = Number(bleed) || 0;
    if (mix <= 0 || n === 0) return frame;
    const out = new Array(n);
    for (let i = 0; i < n; i += 1) {
      const prev = frame[(i - 1 + n) % n];
      const cur = frame[i];
      const nxt = frame[(i + 1) % n];
      const px = [0, 0, 0];
      for (let c = 0; c < 3; c += 1) {
        px[c] = Math.max(0, Math.min(255, Math.round(
          (1 - mix) * cur[c] + (mix / 2) * (prev[c] + nxt[c]),
        )));
      }
      out[i] = px;
    }
    return out;
  }

  // --- drawing ---------------------------------------------------------------
  function drawRoom(f) {
    ctx.fillStyle = "#08090c";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#101218";
    ctx.strokeStyle = "#2a2e3a";
    ctx.lineWidth = 1;
    ctx.fillRect(f.ox, f.oy, f.w * f.scale, f.h * f.scale);
    ctx.strokeRect(f.ox, f.oy, f.w * f.scale, f.h * f.scale);
  }

  function drawFrame(frame) {
    const f = fit();
    drawRoom(f);
    const seg = Number(profile.segments) || 60;
    const count = Math.min(seg, frame.length);

    // Photometric transform then ring bleed (order matches the engine's docs).
    const transformed = [];
    for (let i = 0; i < count; i += 1) transformed.push(transformColor(frame[i]));
    const shaped = applyBleed(transformed, profile.bleed);

    const perimeterMm = 2 * (f.w + f.h);
    const segLenMm = perimeterMm / seg;
    const diffusion = Math.max(0.1, Number(profile.diffusion_width_seg) || 1);
    const diffPx = Math.max(2, diffusion * segLenMm * f.scale);
    const reachMm = Math.max(0, Number(profile.wash_reach_mm) || 0);
    const washGain = Math.max(0, Number(profile.wash_gain) || 0);

    ctx.save();
    ctx.globalCompositeOperation = "lighter";

    // Wash pass first (indirect room glow behind the strip line).
    if (reachMm > 0 && washGain > 0) {
      for (let i = 0; i < count; i += 1) {
        const [r, g, b] = shaped[i];
        const luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
        const alpha = Math.min(1, luma * washGain * 0.55);
        if (alpha <= 0.003) continue;
        const p = stripPosToPoint(i + 0.5);
        const nrm = INWARD_NORMALS[p.wallIndex];
        const cxMm = p.x + nrm[0] * reachMm * 0.35;
        const cyMm = p.y + nrm[1] * reachMm * 0.35;
        const [cx, cy] = toCanvas(f, cxMm, cyMm);
        const radius = Math.max(4, reachMm * f.scale);
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
        grad.addColorStop(0, `rgba(${r},${g},${b},${alpha})`);
        grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // Strip pass: per segment a glow band along its wall span, linear gradient
    // across diffusion_width_seg.
    for (let i = 0; i < count; i += 1) {
      const [r, g, b] = shaped[i];
      if (r === 0 && g === 0 && b === 0) continue;
      const p0 = stripPosToPoint(i);
      const p1 = stripPosToPoint((i + 1) % seg);
      const [x0, y0] = toCanvas(f, p0.x, p0.y);
      const [x1, y1] = toCanvas(f, p1.x, p1.y);
      const midX = (x0 + x1) / 2;
      const midY = (y0 + y1) / 2;
      const angle = Math.atan2(y1 - y0, x1 - x0);
      const len = Math.hypot(x1 - x0, y1 - y0);
      ctx.save();
      ctx.translate(midX, midY);
      ctx.rotate(angle);
      const grad = ctx.createLinearGradient(0, -diffPx / 2, 0, diffPx / 2);
      grad.addColorStop(0, `rgba(${r},${g},${b},0)`);
      grad.addColorStop(0.5, `rgba(${r},${g},${b},0.95)`);
      grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
      ctx.fillStyle = grad;
      ctx.fillRect(-len / 2, -diffPx / 2, len, diffPx);
      ctx.restore();
    }

    ctx.restore();

    if (profile._calibrating) drawCalibrationOverlay(f);
  }

  const HANDLE_R = 9;

  function drawCalibrationOverlay(f) {
    const cs = profile.corner_segments || [0, 15, 30, 45];
    ctx.save();
    ctx.font = "12px system-ui, sans-serif";
    ctx.textAlign = "center";

    // Corner handles: where strip positions corner_segments[k] sit (the room corners).
    for (let k = 0; k < 4; k += 1) {
      const p = stripPosToPoint(cs[k]);
      const [x, y] = toCanvas(f, p.x, p.y);
      ctx.beginPath();
      ctx.arc(x, y, HANDLE_R, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(80, 170, 255, 0.25)";
      ctx.fill();
      ctx.strokeStyle = "#54aaff";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = "#9fd0ff";
      ctx.fillText(`c${k} @ ${cs[k].toFixed(1)}`, x, y - HANDLE_R - 4);
    }

    // Start handle: where strip position 0 (segment 0) sits.
    const s0 = stripPosToPoint(0);
    const [sx, sy] = toCanvas(f, s0.x, s0.y);
    ctx.beginPath();
    ctx.rect(sx - HANDLE_R, sy - HANDLE_R, HANDLE_R * 2, HANDLE_R * 2);
    ctx.fillStyle = "rgba(120, 255, 170, 0.25)";
    ctx.fill();
    ctx.strokeStyle = "#5aff9c";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#a8ffc9";
    ctx.fillText("seg 0", sx, sy + HANDLE_R + 14);

    // Direction arrow: travel direction just after segment 0. Click to flip.
    const ahead = stripPosToPoint(2.0);
    const nrm = INWARD_NORMALS[ahead.wallIndex];
    const inset = 26; // px, inward from the strip line
    const [bx, by] = toCanvas(f, ahead.x, ahead.y);
    const ax = bx + nrm[0] * inset;
    const ay = by + nrm[1] * inset;
    const [tx, ty] = ahead.tangent;
    directionHitCenter = [ax, ay];
    ctx.beginPath();
    ctx.moveTo(ax - tx * 16, ay - ty * 16);
    ctx.lineTo(ax + tx * 16, ay + ty * 16);
    ctx.strokeStyle = "#ffd166";
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(ax + tx * 22, ay + ty * 22);
    ctx.lineTo(ax + tx * 8 - ty * 7, ay + ty * 8 + tx * 7);
    ctx.lineTo(ax + tx * 8 + ty * 7, ay + ty * 8 - tx * 7);
    ctx.closePath();
    ctx.fillStyle = "#ffd166";
    ctx.fill();
    ctx.fillStyle = "#ffe4a3";
    ctx.fillText(profile.direction === "ccw" ? "ccw (click to flip)" : "cw (click to flip)", ax, ay - 14);
    ctx.restore();
  }

  // --- public API ----------------------------------------------------------------
  return {
    renderFrame(frame) {
      lastFrame = frame;
      drawFrame(frame || []);
    },

    setProfile(next) {
      profile = JSON.parse(JSON.stringify(next || {}));
      if (lastFrame) drawFrame(lastFrame);
      else drawFrame([]);
    },

    hitTest(x, y) {
      const f = fit();
      const seg = Number(profile.segments) || 60;
      const perimeterPx = 2 * (f.w + f.h) * f.scale;
      const segPerPx = seg / perimeterPx;
      const cs = profile.corner_segments || [0, 15, 30, 45];
      if (profile._calibrating && directionHitCenter) {
        const [dxc, dyc] = directionHitCenter;
        if (Math.hypot(x - dxc, y - dyc) <= 24) return { type: "direction" };
      }
      for (let k = 0; k < 4; k += 1) {
        const p = stripPosToPoint(cs[k]);
        const [hx, hy] = toCanvas(f, p.x, p.y);
        if (Math.hypot(x - hx, y - hy) <= HANDLE_R + 4) {
          return { type: "corner", index: k, tangent: p.tangent, segPerPx };
        }
      }
      const s0 = stripPosToPoint(0);
      const [sx, sy] = toCanvas(f, s0.x, s0.y);
      if (Math.abs(x - sx) <= HANDLE_R + 4 && Math.abs(y - sy) <= HANDLE_R + 4) {
        return { type: "start", tangent: s0.tangent, segPerPx };
      }
      return null;
    },

    destroy() {
      lastFrame = null;
      directionHitCenter = null;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    },
  };
}

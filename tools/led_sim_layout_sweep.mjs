#!/usr/bin/env node
/**
 * AWR-249 layout sweep — H612D LED Studio shell hardening gate.
 *
 * Widths 900→1728 step 100 × heights 700/900. Asserts:
 * - no horizontal viewport overflow
 * - .route-tabs stays inside .topbar and does not intersect .stage/.canvas
 * - #fixture-canvas drawing rect does not intersect .stage-hud text
 * - ≥900px keeps a two-column app-grid (sidecar beside stage)
 *
 * Requires: system Chrome + playwright-core (e.g. NODE_PATH=/tmp/node_modules).
 *   NODE_PATH=/tmp/node_modules node tools/led_sim_layout_sweep.mjs
 */
import {createServer} from "node:http";
import {readFileSync, existsSync} from "node:fs";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {createRequire} from "node:module";

// Dev-only dependency: prefer NODE_PATH=/tmp/node_modules after `npm i playwright-core` in /tmp.
const require = createRequire("/tmp/package.json");
const {chromium} = require("playwright-core");

const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS = join(__dirname, "led_sim_assets");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const WIDTHS = [];
for (let w = 900; w <= 1728; w += 100) WIDTHS.push(w);
if (WIDTHS[WIDTHS.length - 1] !== 1728) WIDTHS.push(1728);
const HEIGHTS = [700, 900];

const STUB_CATALOG = {
  profile: {
    schema: 2,
    segments: 60,
    physical_leds: 360,
    leds_per_segment: 6,
    strip_length_mm: 14996.16,
    layouts: {
      Home: {
        preset: "perimeter",
        points_mm: [[0, 0], [5216, 0], [5216, 2284], [0, 2284], [0, 0]],
        flip_chain: false,
        room_mm: [5216, 2284],
        layout_locked: false,
      },
    },
    active_layout: "Home",
    gamma: 1,
    white_point: [1, 1, 1],
    brightness: 1,
    glow_radius: 1,
    glow_gain: 1,
    bleed: 0,
    fps: 60,
    latency_ms: 0,
    hold_mode: "zoh",
    slew_ms: 0,
    bpm: 128,
    calibration_status: "unmeasured",
    calibration_domains: {color: "unmeasured", timing: "unmeasured", spatial: "unmeasured"},
    calibration_evidence: {},
    calibration_locked: false,
  },
  profile_error: "",
  profile_warnings: [],
  effects: {beat_chase: {}},
  looks: {ok: true, looks: {}},
  lab: {ok: false},
  lab_error: "",
  device: {physical_leds: 360, leds_per_segment: 6},
  calibration_sequences: {},
  calibration_sequence_version: "h612d-cal-v2",
  calibration_capture_fps: [10, 20, 30, 40, 60],
};

function contentType(path) {
  if (path.endsWith(".html")) return "text/html; charset=utf-8";
  if (path.endsWith(".css")) return "text/css; charset=utf-8";
  if (path.endsWith(".js")) return "text/javascript; charset=utf-8";
  if (path.endsWith(".woff2")) return "font/woff2";
  return "application/octet-stream";
}

function startStaticServer() {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      let url = (req.url || "/").split("?")[0];
      if (url === "/") url = "/index.html";
      if (url.startsWith("/api/")) {
        const body = url === "/api/catalog" ? STUB_CATALOG : {ok: true, profile: STUB_CATALOG.profile};
        res.writeHead(200, {"Content-Type": "application/json"});
        res.end(JSON.stringify(body));
        return;
      }
      const filePath = join(ASSETS, url.replace(/^\//, ""));
      if (!existsSync(filePath)) {
        res.writeHead(404);
        res.end("missing");
        return;
      }
      res.writeHead(200, {"Content-Type": contentType(filePath)});
      res.end(readFileSync(filePath));
    });
    server.listen(0, "127.0.0.1", () => {
      resolve({server, port: server.address().port});
    });
  });
}

const MEASURE_JS = () => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const issues = [];
  if (document.documentElement.scrollWidth > vw + 1 || document.body.scrollWidth > vw + 1) {
    issues.push("horizontal_overflow");
  }

  function rect(el) {
    if (!el || el.hidden) return null;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return null;
    return {x: r.left, y: r.top, w: r.width, h: r.height, b: r.bottom, right: r.right};
  }
  function overlap(a, b) {
    if (!a || !b) return false;
    return !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
  }

  const nav = document.querySelector(".route-tabs");
  const stage = document.querySelector(".stage");
  const canvas = document.querySelector("#fixture-canvas");
  const hud = document.querySelector(".stage-hud");
  const marker = document.querySelector("#marker-label");
  const provenance = document.querySelector("#stage-provenance");
  const topbar = document.querySelector(".topbar");
  const appGrid = document.querySelector(".app-grid");

  const navR = rect(nav);
  const stageR = rect(stage);
  const canvasR = rect(canvas);
  const hudR = rect(hud);
  const markerR = rect(marker);
  const provR = provenance && getComputedStyle(provenance).display !== "none" ? rect(provenance) : null;
  const topbarR = rect(topbar);

  if (navR && stageR && overlap(navR, stageR)) issues.push("nav_intersects_stage");
  if (navR && canvasR && overlap(navR, canvasR)) issues.push("nav_intersects_canvas");
  if (topbarR && canvasR && overlap(topbarR, canvasR)) issues.push("topbar_intersects_canvas");
  if (canvasR && hudR && overlap(canvasR, hudR)) issues.push("canvas_intersects_hud");
  if (canvasR && markerR && overlap(canvasR, markerR)) issues.push("canvas_intersects_marker");
  if (canvasR && provR && overlap(canvasR, provR)) issues.push("canvas_intersects_provenance");

  if (vw >= 900 && appGrid) {
    const cols = getComputedStyle(appGrid).gridTemplateColumns.trim().split(/\s+/);
    if (cols.length < 2) issues.push("desktop_grid_not_two_columns");
  }

  if (navR && topbarR) {
    if (navR.y < topbarR.y - 1 || navR.b > topbarR.b + 1) issues.push("nav_outside_topbar");
    if (navR.x < -1 || navR.right > vw + 1) issues.push("nav_clipped_horizontally");
  }

  return {vw, vh, issues, hudCompact: stage?.classList.contains("hud-compact") || false};
};

async function main() {
  if (!existsSync(CHROME)) {
    console.error("Google Chrome not found");
    process.exit(2);
  }
  const {server, port} = await startStaticServer();
  const failures = [];
  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
    args: ["--disable-gpu"],
  });
  try {
    const page = await browser.newPage();
    for (const height of HEIGHTS) {
      for (const width of WIDTHS) {
        await page.setViewportSize({width, height});
        await page.goto(`http://127.0.0.1:${port}/`, {waitUntil: "networkidle", timeout: 30000});
        await page.waitForTimeout(250);
        const measurement = await page.evaluate(MEASURE_JS);
        if (measurement.issues.length) {
          failures.push({width, height, issues: measurement.issues});
          console.log(`${width}x${height}: FAIL ${measurement.issues.join(",")}`);
        } else {
          console.log(`${width}x${height}: ok`);
        }
      }
    }
  } finally {
    await browser.close();
    server.close();
  }

  console.log("---");
  console.log(`checked ${WIDTHS.length * HEIGHTS.length} viewports; failures ${failures.length}`);
  if (failures.length) {
    console.error(JSON.stringify(failures, null, 2));
    process.exit(1);
  }
  console.log("layout sweep PASS");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

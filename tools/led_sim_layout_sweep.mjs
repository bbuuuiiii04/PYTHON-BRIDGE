#!/usr/bin/env node
/**
 * AWR-249 throwaway layout sweep for H612D LED Studio.
 * Drives widths 900→1728 (100px) × heights 700/900 and asserts:
 * - no horizontal viewport overflow
 * - route-tabs do not intersect the stage/canvas
 * - canvas drawing rect does not intersect HUD text rects
 *
 * Usage (from repo root, sim must be reachable OR we spawn a temp server):
 *   node tools/led_sim_layout_sweep.mjs
 */
import {spawn} from "node:child_process";
import {createServer} from "node:http";
import {readFileSync, existsSync} from "node:fs";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import {tmpdir} from "node:os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS = join(__dirname, "led_sim_assets");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const WIDTHS = [];
for (let w = 900; w <= 1728; w += 100) WIDTHS.push(w);
const HEIGHTS = [700, 900];

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
      // Fail-soft stub APIs so boot does not hang.
      if (url.startsWith("/api/")) {
        const stub = {
          "/api/catalog": {
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
          },
        };
        const body = stub[url] || {ok: true};
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

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function withChrome(userDataDir, port, fn) {
  const debugPort = 9222 + Math.floor(Math.random() * 1000);
  const chrome = spawn(CHROME, [
    `--remote-debugging-port=${debugPort}`,
    `--user-data-dir=${userDataDir}`,
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    `http://127.0.0.1:${port}/`,
  ], {stdio: "ignore"});

  // Wait for CDP
  let version = null;
  for (let i = 0; i < 40; i += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${debugPort}/json/version`);
      if (res.ok) {
        version = await res.json();
        break;
      }
    } catch (_) {
      /* retry */
    }
    await sleep(100);
  }
  if (!version) {
    chrome.kill("SIGKILL");
    throw new Error("Chrome CDP did not come up");
  }

  try {
    return await fn(debugPort);
  } finally {
    chrome.kill("SIGKILL");
  }
}

async function cdpEval(wsUrl, expression) {
  const {default: WebSocket} = await import("node:ws").catch(() => ({default: null}));
  // Prefer undici/websocket via Chrome fetch HTTP endpoint for /json/runtime/evaluate — use Target.
  // Minimal CDP over WebSocket without deps: use chrome's HTTP /json/list + puppeteer-free eval via
  // Runtime.evaluate after attaching.
  const {WebSocket: WS} = await import("ws").catch(() => ({}));
  if (!WS && !WebSocket) {
    // Fallback: use Chrome DevTools Protocol via fetch to /json/new is gone; install note.
    throw new Error("Need the 'ws' package OR use the chrome-eval fallback");
  }
  const Sock = WS || WebSocket;
  return new Promise((resolve, reject) => {
    const sock = new Sock(wsUrl);
    let id = 0;
    const pending = new Map();
    sock.on("open", () => {
      const send = (method, params = {}) => {
        id += 1;
        return new Promise((res, rej) => {
          pending.set(id, {res, rej});
          sock.send(JSON.stringify({id, method, params}));
        });
      };
      (async () => {
        await send("Runtime.enable");
        const result = await send("Runtime.evaluate", {
          expression,
          awaitPromise: true,
          returnByValue: true,
        });
        sock.close();
        if (result.exceptionDetails) {
          reject(new Error(JSON.stringify(result.exceptionDetails)));
        } else {
          resolve(result.result?.value);
        }
      })().catch(reject);
    });
    sock.on("message", (data) => {
      const msg = JSON.parse(String(data));
      if (msg.id && pending.has(msg.id)) {
        const {res} = pending.get(msg.id);
        pending.delete(msg.id);
        res(msg.result || msg);
      }
    });
    sock.on("error", reject);
  });
}

const MEASURE_JS = `(() => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const issues = [];
  const overflowX = document.documentElement.scrollWidth > vw + 1
    || document.body.scrollWidth > vw + 1;
  if (overflowX) issues.push("horizontal_overflow");

  const nav = document.querySelector(".route-tabs");
  const stage = document.querySelector(".stage");
  const canvas = document.querySelector("#fixture-canvas");
  const hud = document.querySelector(".stage-hud");
  const marker = document.querySelector("#marker-label");
  const provenance = document.querySelector("#stage-provenance");
  const topbar = document.querySelector(".topbar");
  const appGrid = document.querySelector(".app-grid");

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

  // Desktop contract ≥900: sidecar beside stage (not stacked full-width sheet).
  if (vw >= 900 && appGrid) {
    const style = getComputedStyle(appGrid);
    const cols = style.gridTemplateColumns.split(" ").filter(Boolean);
    if (cols.length < 2) issues.push("desktop_grid_not_two_columns");
  }

  // Nav must be fully inside topbar vertically (not clipped under stage).
  if (navR && topbarR) {
    if (navR.y < topbarR.y - 1 || navR.b > topbarR.b + 1) {
      issues.push("nav_outside_topbar");
    }
    if (navR.x < -1 || navR.right > vw + 1) issues.push("nav_clipped_horizontally");
  }

  return {
    vw, vh, issues,
    sidecar: !!document.querySelector(".sidecar"),
    hudCompact: stage?.classList.contains("hud-compact") || false,
  };
})()`;

async function main() {
  if (!existsSync(CHROME)) {
    console.error("Google Chrome not found at", CHROME);
    process.exit(2);
  }

  // Prefer ws from npm if present; otherwise use chrome-remote-interface-free approach via fetch + Target.
  let useWs = true;
  try {
    await import("ws");
  } catch {
    useWs = false;
  }

  const {server, port} = await startStaticServer();
  const userDataDir = join(tmpdir(), `led-sim-sweep-${process.pid}`);
  const failures = [];
  const results = [];

  try {
    await withChrome(userDataDir, port, async (debugPort) => {
      const list = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
      const page = list.find((t) => t.type === "page") || list[0];
      if (!page?.webSocketDebuggerUrl) throw new Error("No CDP page target");

      for (const height of HEIGHTS) {
        for (const width of WIDTHS) {
          // Emulate viewport via CDP
          const {default: WS} = await import("ws");
          const measurement = await new Promise((resolve, reject) => {
            const sock = new WS(page.webSocketDebuggerUrl);
            let id = 0;
            const pending = new Map();
            const send = (method, params = {}) => {
              id += 1;
              const msgId = id;
              return new Promise((res, rej) => {
                pending.set(msgId, {res, rej});
                sock.send(JSON.stringify({id: msgId, method, params}));
              });
            };
            sock.on("open", async () => {
              try {
                await send("Runtime.enable");
                await send("Emulation.setDeviceMetricsOverride", {
                  width, height, deviceScaleFactor: 1, mobile: false,
                });
                await send("Page.reload", {ignoreCache: true});
                await sleep(400);
                const evaluated = await send("Runtime.evaluate", {
                  expression: MEASURE_JS,
                  awaitPromise: true,
                  returnByValue: true,
                });
                sock.close();
                if (evaluated.exceptionDetails) {
                  reject(new Error(JSON.stringify(evaluated.exceptionDetails)));
                } else {
                  resolve(evaluated.result.value);
                }
              } catch (err) {
                reject(err);
              }
            });
            sock.on("message", (data) => {
              const msg = JSON.parse(String(data));
              if (msg.id && pending.has(msg.id)) {
                const {res} = pending.get(msg.id);
                pending.delete(msg.id);
                res(msg.result || msg);
              }
            });
            sock.on("error", reject);
          });

          results.push({width, height, ...measurement});
          if (measurement.issues?.length) {
            failures.push({width, height, issues: measurement.issues});
          }
          process.stdout.write(
            `${width}x${height}: ${measurement.issues?.length ? "FAIL " + measurement.issues.join(",") : "ok"}\n`,
          );
        }
      }
    });
  } finally {
    server.close();
  }

  if (!useWs) {
    console.error("Install ws: npm install ws (dev) — required for CDP");
  }

  console.log("---");
  console.log(`checked ${results.length} viewports; failures ${failures.length}`);
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

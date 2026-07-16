#!/usr/bin/env node
/**
 * AWR-273 R9c journey (headless, dry-run pad).
 *
 * 1) /lab → 302 Location: /?view=lab (never 404); shell lands on lab view
 * 2) Lab Play-once: loop=false, one cue length then idle (playback status)
 * 3) Stop mid-cue clears playing
 * 4) Pad tile Play still honors session Loop=true
 * 5) Mirror SSE still streams during Play-once
 *
 *   NODE_PATH=/tmp/node_modules node tools/awr273_live_fire_journey.mjs
 */
import {spawn} from "node:child_process";
import {createRequire} from "node:module";
import {mkdtempSync, writeFileSync, mkdirSync, cpSync, existsSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";
import http from "node:http";

const require = createRequire("/tmp/package.json");
const {chromium} = require("playwright-core");

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = process.env.PYTHON || "python3";

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function httpRaw(port, method, path, body) {
  return new Promise((resolve, reject) => {
    const data = body == null ? null : JSON.stringify(body);
    const req = http.request(
      {
        host: "127.0.0.1",
        port,
        path,
        method,
        headers: data
          ? {"Content-Type": "application/json", "Content-Length": Buffer.byteLength(data)}
          : {},
        timeout: 15000,
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          resolve({
            status: res.statusCode,
            headers: res.headers,
            body: Buffer.concat(chunks).toString("utf8"),
          });
        });
      },
    );
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
}

async function httpJson(port, method, path, body) {
  const res = await httpRaw(port, method, path, body);
  let parsed = {};
  try {
    parsed = JSON.parse(res.body || "{}");
  } catch (err) {
    throw new Error(`${method} ${path} bad JSON: ${res.body.slice(0, 200)}`);
  }
  return {status: res.status, body: parsed, headers: res.headers};
}

async function waitPort(port, path = "/api/access", attempts = 40) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const res = await httpJson(port, "GET", path);
      if (res.status === 200) return;
    } catch (_) { /* retry */ }
    await sleep(150);
  }
  throw new Error(`port ${port} never became ready`);
}

function spawnPython(args, env = {}) {
  const child = spawn(PY, args, {
    cwd: ROOT,
    env: {...process.env, ...env, PYTHONPATH: join(ROOT, "..")},
    stdio: ["ignore", "pipe", "pipe"],
  });
  child._buf = "";
  child.stderr.on("data", (d) => { child._buf += d.toString(); });
  child.stdout.on("data", (d) => { child._buf += d.toString(); });
  return child;
}

async function freePort() {
  return new Promise((resolve) => {
    const s = http.createServer();
    s.listen(0, "127.0.0.1", () => {
      const {port} = s.address();
      s.close(() => resolve(port));
    });
  });
}

async function waitIdle(port, attempts = 40) {
  for (let i = 0; i < attempts; i += 1) {
    const rt = await httpJson(port, "GET", "/api/runtime_status");
    if (!rt.body.playback || !rt.body.playback.playing) return rt.body;
    await sleep(100);
  }
  throw new Error("playback never went idle");
}

async function main() {
  if (!existsSync(CHROME)) {
    console.error("Google Chrome not found");
    process.exit(2);
  }

  const tmp = mkdtempSync(join(tmpdir(), "awr273-"));
  const padCfg = join(tmp, "led_look_director.json");
  const labDir = join(tmp, "led_lab");
  mkdirSync(labDir, {recursive: true});
  cpSync(join(ROOT, "config/led_look_director.example.json"), padCfg);
  writeFileSync(
    join(labDir, "effects_lab.py"),
    "def pulse(beat_pos, local_t, frame_index, params, segments, seed):\n"
      + "    return [[params.get('level', 1.0), 0, 0, 0, 0, 0] for _ in range(segments)]\n"
      + "LAB_EFFECTS = {'pulse': ('slot', pulse)}\n",
    "utf8",
  );
  writeFileSync(
    join(labDir, "drafts.json"),
    JSON.stringify({
      entries: [
        {
          name: "pulse", kind: "slot", fn: "pulse", params: {level: 0.5},
          cue_beats: 2, brief: "r9c one-shot", notes: "", status: "iterating",
          timing_mode: "beat", target_role: "", created: "2026-01-01T00:00:00+00:00",
          updated: "2026-01-01T00:00:00+00:00",
          param_specs: {level: {kind: "slider", label: "Level", min: 0, max: 1, step: 0.05}},
        },
      ],
    }, null, 2),
    "utf8",
  );

  const padPort = await freePort();
  const padBoot = join(tmp, "pad_boot.py");
  writeFileSync(
    padBoot,
    `
import sys
from pathlib import Path
sys.path.insert(0, ${JSON.stringify(join(ROOT, ".."))})
from http.server import ThreadingHTTPServer
from rb_ss_bridge_v2.tools.led_pad_web import LedPadService, build_handler
svc = LedPadService(
    ${JSON.stringify(padCfg)},
    dry_run=True,
    lab_dir=Path(${JSON.stringify(labDir)}),
)
httpd = ThreadingHTTPServer(("127.0.0.1", ${padPort}), build_handler(svc))
print("PAD_READY", flush=True)
httpd.serve_forever()
`,
    "utf8",
  );

  const pad = spawnPython([padBoot]);
  const fail = (msg) => {
    try { pad.kill("SIGTERM"); } catch (_) {}
    console.error(msg);
    console.error(pad._buf.slice(-800));
    process.exit(1);
  };

  try {
    await waitPort(padPort, "/api/lab/list");
  } catch (err) {
    fail(String(err));
  }

  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
    args: ["--disable-gpu"],
  });
  const failures = [];

  try {
    // (1) /lab redirect
    const redir = await httpRaw(padPort, "GET", "/lab");
    if (redir.status !== 302) failures.push(`(1) /lab status ${redir.status} (want 302)`);
    if ((redir.headers.location || "") !== "/?view=lab") {
      failures.push(`(1) Location ${redir.headers.location}`);
    }
    const page = await browser.newPage();
    const resp = await page.goto(`http://127.0.0.1:${padPort}/lab`, {waitUntil: "networkidle"});
    if (!resp || resp.status() !== 200) failures.push(`(1) follow status ${resp && resp.status()}`);
    const land = await page.evaluate(() => ({
      path: location.pathname + location.search,
      view: document.body.dataset.shellView,
      playLabel: (document.getElementById("playDraftBtn") || {}).textContent || "",
      previewPrimary: (document.getElementById("previewBtn") || {}).classList.contains("primary"),
      playPrimary: (document.getElementById("playDraftBtn") || {}).classList.contains("primary"),
    }));
    if (land.path !== "/?view=lab") failures.push(`(1) land path ${land.path}`);
    if (land.view !== "lab") failures.push(`(1) shellView ${land.view}`);
    if (!/Play once on lights/i.test(land.playLabel)) failures.push(`(1) play label ${land.playLabel}`);
    if (!land.previewPrimary || land.playPrimary) {
      failures.push(`(1) verb hierarchy: ${JSON.stringify(land)}`);
    }
    if (!failures.find((f) => f.startsWith("(1)"))) console.log("(1) /lab 302 → /?view=lab shell: ok");

    // (2) Play-once one cue then stop
    await httpJson(padPort, "POST", "/api/session", {bpm: 240, loop: true});
    const play = await httpJson(padPort, "POST", "/api/lab/play", {name: "pulse", cue_beats: 2});
    if (play.status !== 200 || !play.body.ok) failures.push(`(2) lab play ${JSON.stringify(play.body)}`);
    if (play.body.loop !== false || (play.body.playback && play.body.playback.loop !== false)) {
      failures.push(`(2) lab play not one-shot: ${JSON.stringify(play.body)}`);
    }
    const mid = await httpJson(padPort, "GET", "/api/runtime_status");
    if (!mid.body.playback || !mid.body.playback.playing) failures.push("(2) expected playing mid-cue");
    try {
      await waitIdle(padPort, 50);
      console.log("(2) Play-once auto-stops after cue: ok");
    } catch (err) {
      failures.push(`(2) ${err.message}`);
    }

    // (3) Stop mid-cue
    await httpJson(padPort, "POST", "/api/lab/play", {name: "pulse", cue_beats: 16});
    const beforeStop = await httpJson(padPort, "GET", "/api/runtime_status");
    if (!beforeStop.body.playback || !beforeStop.body.playback.playing) {
      failures.push("(3) expected playing before stop");
    }
    await httpJson(padPort, "POST", "/api/stop", {});
    const afterStop = await httpJson(padPort, "GET", "/api/runtime_status");
    if (afterStop.body.playback && afterStop.body.playback.playing) {
      failures.push("(3) still playing after stop");
    } else if (!failures.find((f) => f.startsWith("(3)"))) {
      console.log("(3) Stop mid-cue: ok");
    }

    // (4) Pad tile Play keeps session loop
    const padPlay = await httpJson(padPort, "POST", "/api/play", {name: "rt_groove_chase"});
    if (!padPlay.body.ok) failures.push(`(4) pad play ${JSON.stringify(padPlay.body)}`);
    if (!padPlay.body.playback || padPlay.body.playback.loop !== true) {
      failures.push(`(4) pad play loop expected true: ${JSON.stringify(padPlay.body.playback)}`);
    } else {
      console.log("(4) pad tile Play still loops with session Loop: ok");
    }
    await httpJson(padPort, "POST", "/api/stop", {});

    // (5) Mirror streams during Play-once
    const mirrorOk = await new Promise((resolve) => {
      const req = http.request(
        {host: "127.0.0.1", port: padPort, path: "/api/mirror/stream", method: "GET", timeout: 5000},
        (res) => {
          if (res.statusCode !== 200) {
            resolve(false);
            res.resume();
            return;
          }
          let buf = "";
          let saw = false;
          res.on("data", (chunk) => {
            buf += chunk.toString("utf8");
            if (buf.includes("data:") && buf.includes("playing")) saw = true;
          });
          setTimeout(() => {
            req.destroy();
            resolve(saw);
          }, 800);
        },
      );
      req.on("error", () => resolve(false));
      req.end();
      httpJson(padPort, "POST", "/api/lab/play", {name: "pulse", cue_beats: 8}).catch(() => {});
    });
    if (!mirrorOk) failures.push("(5) mirror SSE silent during Play-once");
    else console.log("(5) mirror streams during Play-once: ok");
    await httpJson(padPort, "POST", "/api/stop", {});
  } catch (err) {
    failures.push(String(err && err.stack || err));
  } finally {
    await browser.close().catch(() => {});
    try { pad.kill("SIGTERM"); } catch (_) {}
  }

  if (failures.length) {
    console.error("AWR-273 FAIL:");
    for (const f of failures) console.error(" -", f);
    process.exit(1);
  }
  console.log("AWR-273 PASS");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

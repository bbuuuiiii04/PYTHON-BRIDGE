#!/usr/bin/env node
/**
 * AWR-271 R9a shell journey (headless).
 *
 * 1) Pad shell → Lab tab switches in-place (no full document swap)
 * 2) /lab 302-redirects to /?view=lab (R9c) and lands on the lab view
 * 3) Draft select → Preview paints
 * 4) Accept still wires (phrase survives reopen) on the merged component
 *
 *   NODE_PATH=/tmp/node_modules node tools/awr271_shell_journey.mjs
 */
import {spawn} from "node:child_process";
import {createRequire} from "node:module";
import {mkdtempSync, readFileSync, writeFileSync, mkdirSync, cpSync, existsSync} from "node:fs";
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

function httpJson(port, method, path, body) {
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
          const raw = Buffer.concat(chunks).toString("utf8");
          try {
            resolve({status: res.statusCode, body: JSON.parse(raw || "{}")});
          } catch (err) {
            reject(new Error(`${method} ${path} bad JSON: ${raw.slice(0, 200)}`));
          }
        });
      },
    );
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
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

async function main() {
  if (!existsSync(CHROME)) {
    console.error("Google Chrome not found");
    process.exit(2);
  }

  const tmp = mkdtempSync(join(tmpdir(), "awr271-"));
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
          name: "pulse", kind: "slot", fn: "pulse", params: {level: 0.4},
          cue_beats: 8, brief: "r9a", notes: "", status: "iterating",
          timing_mode: "beat", target_role: "groove", created: "2026-01-01T00:00:00+00:00",
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
    const page = await browser.newPage();

    // (1) Cold pad → Lab tab in-place
    await page.goto(`http://127.0.0.1:${padPort}/`, {waitUntil: "networkidle"});
    await page.waitForSelector("#view-pad");
    const marker = await page.evaluate(() => {
      window.__awr271 = {alive: true};
      return document.body.dataset.shell;
    });
    if (marker !== "lighting") failures.push("(1) missing data-shell=lighting on /");

    await page.click('a[data-shell-view="lab"]');
    await page.waitForSelector("#view-lab:not([hidden])");
    const afterClick = await page.evaluate(() => ({
      alive: Boolean(window.__awr271 && window.__awr271.alive),
      path: location.pathname + location.search,
      labHidden: document.getElementById("view-lab").hidden,
      padHidden: document.getElementById("view-pad").hidden,
      labRoute: document.body.classList.contains("lab-route"),
      hasEditor: Boolean(window.LabEditor),
    }));
    if (!afterClick.alive) failures.push("(1) full page swap — window marker lost");
    if (afterClick.path !== "/?view=lab") failures.push(`(1) path not /?view=lab: ${afterClick.path}`);
    if (afterClick.labHidden || !afterClick.padHidden) failures.push("(1) view panels wrong after Lab tab");
    if (!afterClick.labRoute) failures.push("(1) body.lab-route not set");
    if (!afterClick.hasEditor) failures.push("(1) LabEditor export missing");
    if (!failures.find((f) => f.startsWith("(1)"))) console.log("(1) pad→Lab in-place shell switch: ok");

    // (2) Direct /lab redirects then lands on lab view
    const page2 = await browser.newPage();
    const resp = await page2.goto(`http://127.0.0.1:${padPort}/lab`, {waitUntil: "networkidle"});
    if (!resp || resp.status() !== 200) failures.push(`(2) /lab follow status ${resp && resp.status()}`);
    const landPath = await page2.evaluate(() => location.pathname + location.search);
    if (landPath !== "/?view=lab") failures.push(`(2) land path ${landPath}`);
    const shell2 = await page2.evaluate(() => ({
      shell: document.body.dataset.shell,
      view: document.body.dataset.shellView,
      hasPad: Boolean(document.getElementById("view-pad")),
      hasLab: Boolean(document.getElementById("view-lab")),
      hasAccept: Boolean(document.getElementById("acceptBtn")),
    }));
    if (shell2.shell !== "lighting" || shell2.view !== "lab" || !shell2.hasPad || !shell2.hasLab || !shell2.hasAccept) {
      failures.push(`(2) /lab shell shape: ${JSON.stringify(shell2)}`);
    } else {
      console.log("(2) /lab 302 → /?view=lab shared shell: ok");
    }

    // (3) draft → preview on merged component
    await page2.waitForSelector("#draftList button.lab-row");
    await page2.click('#draftList button.lab-row[data-name="pulse"]');
    await page2.click("#previewBtn");
    await page2.waitForTimeout(700);
    const preview = await page2.evaluate(() => {
      const hint = document.getElementById("previewHint");
      const canvas = document.getElementById("previewStrip");
      return {
        hintHidden: hint ? hint.hidden : null,
        w: canvas ? canvas.width : 0,
      };
    });
    if (preview.w <= 0) failures.push(`(3) preview canvas not sized: ${JSON.stringify(preview)}`);
    else console.log("(3) draft→preview on merged component: ok");

    // (4) Accept wire-in still works from /lab shell
    await page2.selectOption("#targetRoleSelect", "drop");
    await page2.fill("#briefInput", "r9a accept");
    await page2.click("#acceptBtn");
    await page2.waitForTimeout(600);
    await page2.reload({waitUntil: "networkidle"});
    await page2.fill("#draftSearch", "pulse");
    await page2.click('#draftList button.lab-row[data-name="pulse"]');
    const phrase = await page2.inputValue("#targetRoleSelect");
    const brief = await page2.inputValue("#briefInput");
    const status = await page2.textContent("#statusText");
    const statusOk = /live|accept/i.test(String(status || ""));
    if (phrase !== "drop" || brief !== "r9a accept" || !statusOk) {
      failures.push(`(4) accept reopen failed phrase=${phrase} brief=${brief} status=${status}`);
    } else {
      console.log("(4) accept→reopen on merged shell: ok");
    }
    const disk = JSON.parse(readFileSync(join(labDir, "drafts.json"), "utf8"));
    const pulse = disk.entries.find((e) => e.name === "pulse");
    if (pulse?.target_role !== "drop" || pulse?.status !== "accepted") {
      failures.push(`(4) disk accept: ${JSON.stringify(pulse)}`);
    }

    // (5) Pad tab back in-place from lab
    await page2.click('a[data-shell-view="pad"]');
    await page2.waitForSelector("#view-pad:not([hidden])");
    const back = await page2.evaluate(() => ({
      path: location.pathname,
      padHidden: document.getElementById("view-pad").hidden,
      labHidden: document.getElementById("view-lab").hidden,
    }));
    if (back.path !== "/" || back.padHidden || !back.labHidden) {
      failures.push(`(5) Lab→Pad switch: ${JSON.stringify(back)}`);
    } else {
      console.log("(5) Lab→Pad in-place: ok");
    }
  } catch (err) {
    failures.push(String(err && err.stack || err));
  } finally {
    await browser.close();
    try { pad.kill("SIGTERM"); } catch (_) {}
  }

  if (failures.length) {
    console.error("AWR-271 journey FAILED:");
    for (const f of failures) console.error(" -", f);
    process.exit(1);
  }
  console.log("AWR-271 journey PASS");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

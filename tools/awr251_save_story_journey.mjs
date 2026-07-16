#!/usr/bin/env node
/**
 * AWR-251 save-story journey (headless).
 *
 * (a) Lab: edit phrase → Accept → reopen → phrase survived
 * (b) Lab: drag slider → switch draft → disk unchanged → switch back → editor restored
 * (c) Sim: Save as → cold reload → layout present on disk
 * (d) Sim: picker preview shows picked geometry; editing disabled
 *
 * Requires: system Chrome + playwright-core (NODE_PATH=/tmp/node_modules).
 * Spawns temporary pad (:0) + sim (:0) Python services against temp dirs.
 *
 *   NODE_PATH=/tmp/node_modules node tools/awr251_save_story_journey.mjs
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
    cwd: ROOT.parent ? join(ROOT) : ROOT,
    env: {...process.env, ...env, PYTHONPATH: join(ROOT, "..")},
    stdio: ["ignore", "pipe", "pipe"],
  });
  child._buf = "";
  child.stderr.on("data", (d) => { child._buf += d.toString(); });
  child.stdout.on("data", (d) => { child._buf += d.toString(); });
  return child;
}

async function freePort() {
  // Ask OS for an ephemeral port via a short-lived server.
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

  const tmp = mkdtempSync(join(tmpdir(), "awr251-"));
  const padCfg = join(tmp, "led_look_director.json");
  const labDir = join(tmp, "led_lab");
  const simProfile = join(tmp, "led_sim_profile.json");
  mkdirSync(labDir, {recursive: true});
  cpSync(join(ROOT, "config/led_look_director.example.json"), padCfg);
  writeFileSync(
    join(labDir, "effects_lab.py"),
    "def pulse(beat_pos, local_t, frame_index, params, segments, seed):\n"
      + "    return [[params.get('level', 1.0), 0, 0, 0, 0, 0] for _ in range(segments)]\n"
      + "def other(beat_pos, local_t, frame_index, params, segments, seed):\n"
      + "    return [[0, params.get('level', 1.0), 0, 0, 0, 0] for _ in range(segments)]\n"
      + "LAB_EFFECTS = {'pulse': ('slot', pulse), 'other': ('slot', other)}\n",
    "utf8",
  );
  writeFileSync(
    join(labDir, "drafts.json"),
    JSON.stringify({
      entries: [
        {
          name: "pulse", kind: "slot", fn: "pulse", params: {level: 0.3},
          cue_beats: 8, brief: "old", notes: "", status: "iterating",
          timing_mode: "unknown", target_role: "", created: "2026-01-01T00:00:00+00:00",
          updated: "2026-01-01T00:00:00+00:00",
          param_specs: {level: {kind: "slider", label: "Level", min: 0, max: 1, step: 0.05}},
        },
        {
          name: "other", kind: "slot", fn: "other", params: {level: 0.1},
          cue_beats: 8, brief: "", notes: "", status: "iterating",
          timing_mode: "unknown", target_role: "", created: "2026-01-01T00:00:00+00:00",
          updated: "2026-01-01T00:00:00+00:00",
          param_specs: {level: {kind: "slider", label: "Level", min: 0, max: 1, step: 0.05}},
        },
      ],
    }, null, 2),
    "utf8",
  );
  const example = JSON.parse(readFileSync(join(ROOT, "config/led_sim_profile.example.json"), "utf8"));
  const home = example.layouts.Home;
  const venue = {
    ...JSON.parse(JSON.stringify(home)),
    preset: "snake",
    points_mm: [[0, 0], [2000, 0], [2000, 1000], [0, 1000], [0, 0]],
    room_mm: [2000, 1000],
  };
  example.layouts = {Home: home, Venue: venue};
  example.active_layout = "Home";
  writeFileSync(simProfile, JSON.stringify(example, null, 2), "utf8");

  const padPort = await freePort();
  const simPort = await freePort();

  // Minimal inline pad server via unittest-style bootstrap script.
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
  const simBoot = join(tmp, "sim_boot.py");
  writeFileSync(
    simBoot,
    `
import sys
sys.path.insert(0, ${JSON.stringify(join(ROOT, ".."))})
from rb_ss_bridge_v2.tools.led_sim_web import run_server
print("SIM_READY", flush=True)
run_server(port=${simPort}, profile_path=${JSON.stringify(simProfile)})
`,
    "utf8",
  );

  const pad = spawnPython([padBoot]);
  const sim = spawnPython([simBoot]);
  const kids = [pad, sim];
  const fail = (msg) => {
    for (const c of kids) {
      try { c.kill("SIGTERM"); } catch (_) {}
    }
    console.error(msg);
    console.error("--- pad ---");
    console.error(pad._buf.slice(-800));
    console.error("--- sim ---");
    console.error(sim._buf.slice(-800));
    process.exit(1);
  };

  try {
    await waitPort(padPort, "/api/lab/list");
    await waitPort(simPort, "/api/catalog");
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

    // —— (a) Lab Accept persists phrase ——
    await page.goto(`http://127.0.0.1:${padPort}/lab`, {waitUntil: "networkidle"});
    await page.waitForSelector("#draftList button.lab-row");
    await page.click('#draftList button.lab-row[data-name="pulse"]');
    await page.selectOption("#targetRoleSelect", "drop");
    await page.selectOption("#timingModeSelect", "beat");
    await page.fill("#briefInput", "journey phrase");
    await page.click("#acceptBtn");
    await page.waitForTimeout(500);
    await page.reload({waitUntil: "networkidle"});
    // Accepted chip is off by default — exact-name search still surfaces the hit (m-8).
    await page.fill("#draftSearch", "pulse");
    await page.click('#draftList button.lab-row[data-name="pulse"]');
    const phrase = await page.inputValue("#targetRoleSelect");
    const brief = await page.inputValue("#briefInput");
    const status = await page.textContent("#statusText");
    if (phrase !== "drop" || brief !== "journey phrase" || !/accept/i.test(String(status || ""))) {
      failures.push(`(a) accept reopen failed phrase=${phrase} brief=${brief} status=${status}`);
    } else {
      console.log("(a) accept→reopen phrase survived: ok");
    }
    const diskA = JSON.parse(readFileSync(join(labDir, "drafts.json"), "utf8"));
    const pulseA = diskA.entries.find((e) => e.name === "pulse");
    if (pulseA?.target_role !== "drop" || pulseA?.status !== "accepted") {
      failures.push(`(a) disk missing accept: ${JSON.stringify(pulseA)}`);
    }

    // —— (b) slider local + switch restores; disk unchanged ——
    await page.fill("#draftSearch", "");
    await page.click('[data-status-filter="accepted"]'); // show accepted pulse
    const beforeB = readFileSync(join(labDir, "drafts.json"), "utf8");
    await page.click('#draftList button.lab-row[data-name="pulse"]');
    const slider = page.locator('#paramControls input[data-param="level"]');
    await slider.waitFor({state: "visible"});
    await slider.fill("0.85");
    await slider.dispatchEvent("input");
    await page.waitForTimeout(600); // debounce auto-apply
    await page.click('#draftList button.lab-row[data-name="other"]');
    await page.waitForTimeout(300);
    const midB = readFileSync(join(labDir, "drafts.json"), "utf8");
    if (midB !== beforeB) {
      failures.push("(b) drafts.json mutated after slider+switch (should be editor-local only)");
    }
    await page.click('#draftList button.lab-row[data-name="pulse"]');
    await page.waitForTimeout(200);
    const restored = await page.locator('#paramControls input[data-param="level"]').inputValue();
    const dirty = await page.textContent("#labDirtyChip");
    if (Math.abs(Number(restored) - 0.85) > 0.001) {
      failures.push(`(b) editor not restored: got ${restored}`);
    } else if (!String(dirty).includes("Unsaved")) {
      failures.push(`(b) dirty badge lying: ${dirty}`);
    } else {
      console.log("(b) slider→switch→restore + disk unchanged: ok");
    }

    // —— (c) Sim Save as persists ——
    await page.goto(`http://127.0.0.1:${simPort}/`, {waitUntil: "networkidle"});
    // AWR-274: Layout lives under Setup (not a top-level tab).
    await page.click("#tab-setup");
    await page.click("#setup-tab-layout");
    await page.click("#layout-save-as");
    await page.waitForSelector("#name-dialog:not([hidden])");
    await page.fill("#name-dialog-input", "Journey Copy");
    await page.click("#name-dialog-ok");
    await page.waitForTimeout(600);
    const afterSaveAs = JSON.parse(readFileSync(simProfile, "utf8"));
    if (!afterSaveAs.layouts["Journey Copy"]) {
      failures.push("(c) Save as did not write Journey Copy to disk");
    } else {
      console.log("(c) save-as→disk: ok");
    }
    // Cold reload via fresh GET through a new page context.
    await page.reload({waitUntil: "networkidle"});
    await page.click("#tab-setup");
    await page.click("#setup-tab-layout");
    const options = await page.$$eval("#layout-slot option", (els) => els.map((e) => e.value));
    if (!options.includes("Journey Copy")) {
      failures.push(`(c) cold reload missing Journey Copy; options=${options.join(",")}`);
    } else {
      console.log("(c) cold reload picker has Journey Copy: ok");
    }

    // —— (d) picker preview geometry + edit disabled ——
    // Ensure Home active, pick Venue.
    await page.selectOption("#layout-slot", "Home");
    // Use Home if needed
    const useEnabled = await page.isEnabled("#layout-use");
    if (useEnabled) {
      await page.click("#layout-use");
      await page.waitForTimeout(400);
    }
    await page.selectOption("#layout-slot", "Venue");
    await page.waitForTimeout(300);
    const previewState = await page.evaluate(() => {
      const wrap = document.getElementById("canvas-wrap");
      const hint = document.getElementById("layout-active-hint");
      const widthDisabled = document.getElementById("room-width-ft")?.disabled;
      const flipDisabled = document.getElementById("layout-flip")?.disabled;
      // Fingerprint drawn layout via view API if exposed on window — fall back to room fields.
      const roomW = document.getElementById("room-width-ft")?.value;
      const roomH = document.getElementById("room-height-ft")?.value;
      return {
        previewingClass: wrap?.classList.contains("previewing-layout"),
        hint: hint?.textContent || "",
        widthDisabled,
        flipDisabled,
        roomW,
        roomH,
      };
    });
    // Venue room is 2000x1000 mm ≈ 6.6 x 3.3 ft
    const venueW = Number(previewState.roomW);
    const venueH = Number(previewState.roomH);
    if (!previewState.previewingClass) {
      failures.push("(d) canvas-wrap missing previewing-layout class");
    }
    if (!String(previewState.hint).toLowerCase().includes("previewing")) {
      failures.push(`(d) hint missing previewing copy: ${previewState.hint}`);
    }
    if (!previewState.widthDisabled || !previewState.flipDisabled) {
      failures.push("(d) edit controls not disabled while previewing");
    }
    if (!(venueW > 5 && venueW < 8 && venueH > 2 && venueH < 5)) {
      failures.push(`(d) form did not show Venue geometry (ft): ${venueW}x${venueH}`);
    } else {
      console.log("(d) picker preview + edits disabled: ok");
    }

    // Fingerprint path via getLayout if view is reachable through evaluate on module scope — skip if not.
  } finally {
    await browser.close();
    for (const c of kids) {
      try { c.kill("SIGTERM"); } catch (_) {}
    }
  }

  console.log("---");
  if (failures.length) {
    console.error(failures.join("\n"));
    process.exit(1);
  }
  console.log("AWR-251 save-story journey PASS");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

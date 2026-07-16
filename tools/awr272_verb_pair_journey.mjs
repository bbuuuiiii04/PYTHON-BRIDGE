#!/usr/bin/env node
/**
 * AWR-272 R9b verb-pair journey (headless).
 *
 * 1) create → preview → Save draft → Accept (look lands in phrase bank)
 * 2) Reject flips status and stays out of the show
 * 3) two-tab CAS: first write wins; second gets 409 stale_entry
 * 4) primary UI no longer shows "Save to show" / scary restart jargon
 *
 *   NODE_PATH=/tmp/node_modules node tools/awr272_verb_pair_journey.mjs
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

  const tmp = mkdtempSync(join(tmpdir(), "awr272-"));
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
          cue_beats: 8, brief: "r9b starter", notes: "", status: "iterating",
          timing_mode: "beat", target_role: "", created: "2026-01-01T00:00:00+00:00",
          updated: "2026-01-01T00:00:00+00:00",
          param_specs: {level: {kind: "slider", label: "Level", min: 0, max: 1, step: 0.05}},
        },
        {
          name: "reject_me", kind: "slot", fn: "pulse", params: {level: 0.2},
          cue_beats: 8, brief: "reject path", notes: "", status: "iterating",
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
    await page.goto(`http://127.0.0.1:${padPort}/?view=lab`, {waitUntil: "networkidle"});

    // —— (0) primary verb copy on merged shell ——
    const verbs = await page.evaluate(() => {
      const text = document.body.innerText;
      return {
        saveDraft: (document.getElementById("saveDraftBtn") || {}).textContent || "",
        accept: (document.getElementById("acceptBtn") || {}).textContent || "",
        reject: (document.getElementById("rejectBtn") || {}).textContent || "",
        hasSaveToShow: /Save to show/i.test(text),
        hasScaryRestart: /Bridge restart required/i.test(text),
        hasPadMore: Boolean(document.getElementById("padMoreActions")),
        commitPrimary: (() => {
          const btn = document.getElementById("commitBtn");
          return btn ? btn.classList.contains("primary") : null;
        })(),
      };
    });
    if (!/Save draft/i.test(verbs.saveDraft)) failures.push(`(0) Save draft label: ${verbs.saveDraft}`);
    if (!/Accept — adds it to your show/i.test(verbs.accept)) failures.push(`(0) Accept label: ${verbs.accept}`);
    if (!/Reject — keep out of show/i.test(verbs.reject)) failures.push(`(0) Reject label: ${verbs.reject}`);
    if (verbs.hasSaveToShow) failures.push("(0) Save to show still in primary UI text");
    if (verbs.hasScaryRestart) failures.push("(0) Bridge restart required still visible");
    if (!verbs.hasPadMore || verbs.commitPrimary) failures.push(`(0) pad push not demoted: ${JSON.stringify(verbs)}`);
    if (!failures.find((f) => f.startsWith("(0)"))) console.log("(0) primary verb pair + demoted pad push: ok");

    // —— (1) create → preview → Save draft → Accept → bank ——
    await page.click("#newDraftBtn");
    await page.waitForSelector('#modalForm input[name="display_name"]');
    await page.fill('#modalForm input[name="display_name"]', "Walkthrough Cue");
    await page.click("#modalActions [data-modal-confirm]");
    await page.waitForTimeout(700);
    const entryName = "walkthrough_cue";
    const selected = await page.evaluate(() => {
      const title = document.getElementById("draftTitle");
      const row = document.querySelector(`#draftList button.lab-row[data-name="walkthrough_cue"]`);
      return {
        title: title ? title.textContent.trim() : "",
        rowOn: row ? row.classList.contains("on") || row.getAttribute("aria-current") : null,
      };
    });
    if (!/walkthrough/i.test(selected.title)) {
      failures.push(`(1) create did not select draft: ${JSON.stringify(selected)}`);
    } else {
      await page.click("#previewBtn");
      await page.waitForTimeout(700);
      const previewW = await page.evaluate(() => {
        const c = document.getElementById("previewStrip");
        return c ? c.width : 0;
      });
      if (previewW <= 0) failures.push("(1) preview did not size canvas");

      await page.selectOption("#targetRoleSelect", "drop");
      await page.fill("#briefInput", "r9b accept journey");
      await page.click("#saveDraftBtn");
      await page.waitForTimeout(500);
      const diskAfterSave = JSON.parse(readFileSync(join(labDir, "drafts.json"), "utf8"));
      const saved = diskAfterSave.entries.find((e) => e.name === entryName);
      if (!saved || saved.status !== "iterating") {
        failures.push(`(1) Save draft disk: ${JSON.stringify(saved)}`);
      } else if (saved.brief !== "r9b accept journey" || saved.target_role !== "drop") {
        failures.push(`(1) Save draft fields: brief=${saved.brief} role=${saved.target_role}`);
      }

      await page.click("#acceptBtn");
      await page.waitForTimeout(900);
      const diskAccept = JSON.parse(readFileSync(join(labDir, "drafts.json"), "utf8"));
      const accepted = diskAccept.entries.find((e) => e.name === entryName);
      if (!accepted || accepted.status !== "accepted") {
        failures.push(`(1) Accept disk status: ${JSON.stringify(accepted)}`);
      }
      const showCfg = JSON.parse(readFileSync(padCfg, "utf8"));
      const look = (showCfg.looks || {})[entryName];
      const dropBank = ((((showCfg.banks || {}).default || {}).drop) || []);
      if (!look || String(look.scene_ref || "") !== `lab:${entryName}`) {
        failures.push(`(1) look missing in show file: ${JSON.stringify(look)}`);
      } else if (!dropBank.includes(entryName)) {
        failures.push(`(1) look not in drop bank: ${JSON.stringify(dropBank)}`);
      } else if (!failures.find((f) => f.startsWith("(1)"))) {
        console.log(`(1) create→preview→Save draft→Accept bank land (${entryName}): ok`);
      }
    }

    // —— (2) Reject flip ——
    await page.fill("#draftSearch", "reject_me");
    await page.click('#draftList button.lab-row[data-name="reject_me"]');
    await page.waitForTimeout(200);
    await page.click("#rejectBtn");
    await page.waitForTimeout(500);
    const diskReject = JSON.parse(readFileSync(join(labDir, "drafts.json"), "utf8"));
    const rejected = diskReject.entries.find((e) => e.name === "reject_me");
    const showAfterReject = JSON.parse(readFileSync(padCfg, "utf8"));
    const rejectLook = (showAfterReject.looks || {}).reject_me;
    if (!rejected || rejected.status !== "rejected") {
      failures.push(`(2) reject disk: ${JSON.stringify(rejected)}`);
    } else if (rejectLook) {
      failures.push("(2) Reject wrote a production look (should not)");
    } else {
      console.log("(2) Reject status flip, stays out of show: ok");
    }

    // —— (3) two-tab CAS race (first-write-wins → 409) ——
    const list = await httpJson(padPort, "GET", "/api/lab/list");
    const pulse = (list.body.entries || []).find((e) => e.name === "pulse");
    if (!pulse || !pulse.updated) {
      failures.push(`(3) missing pulse stamp: ${JSON.stringify(pulse)}`);
    } else {
      const stamp = pulse.updated;
      const first = await httpJson(padPort, "POST", "/api/lab/save", {
        name: "pulse", kind: "slot", fn: "pulse", params: {level: 0.55},
        cue_beats: 8, brief: "cas-first", notes: "", status: "iterating",
        timing_mode: "beat", target_role: "", updated: stamp,
      });
      const second = await httpJson(padPort, "POST", "/api/lab/save", {
        name: "pulse", kind: "slot", fn: "pulse", params: {level: 0.99},
        cue_beats: 8, brief: "cas-second", notes: "", status: "iterating",
        timing_mode: "beat", target_role: "", updated: stamp,
      });
      if (first.status !== 200) {
        failures.push(`(3) first write failed: ${first.status} ${JSON.stringify(first.body)}`);
      } else if (second.status !== 409 || (second.body && second.body.error) !== "stale_entry") {
        failures.push(`(3) second write expected 409 stale_entry, got ${second.status} ${JSON.stringify(second.body)}`);
      } else {
        const after = JSON.parse(readFileSync(join(labDir, "drafts.json"), "utf8"));
        const won = after.entries.find((e) => e.name === "pulse");
        if (!won || won.brief !== "cas-first" || Number(won.params.level) !== 0.55) {
          failures.push(`(3) first-write-wins lost: ${JSON.stringify(won)}`);
        } else {
          console.log("(3) two-tab CAS 409 first-write-wins: ok");
        }
      }
    }
  } catch (err) {
    failures.push(String(err && err.stack || err));
  } finally {
    await browser.close();
    try { pad.kill("SIGTERM"); } catch (_) {}
  }

  if (failures.length) {
    console.error("AWR-272 journey FAILED:");
    for (const f of failures) console.error(" -", f);
    process.exit(1);
  }
  console.log("AWR-272 journey PASS");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

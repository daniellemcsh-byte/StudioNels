/**
 * Force this checkout onto origin/main and verify the no502 Start scripts landed.
 * Used by Pinokio Update — free ports first so Windows file locks don't block git.
 */
const { execSync } = require("child_process")
const fs = require("fs")
const path = require("path")

const BUILD = "2026-11-15-no502"
const root = path.join(__dirname, "..")
const remote = "https://github.com/daniellemcsh-byte/StudioNels.git"

function run(cmd) {
  console.log("$", cmd)
  execSync(cmd, {
    cwd: root,
    stdio: "inherit",
    env: process.env,
    windowsHide: true,
    shell: true,
  })
}

function runCapture(cmd) {
  return execSync(cmd, {
    cwd: root,
    encoding: "utf8",
    env: process.env,
    windowsHide: true,
    shell: true,
  }).trim()
}

console.log(`pull-main build ${BUILD}`)

// Unlock script files held by a previous Start (Windows).
try {
  run("node scripts/free-ports.js")
} catch (err) {
  console.warn("free-ports warning:", err && err.message ? err.message : err)
}

try {
  run(`git remote set-url origin ${remote}`)
} catch {
  try {
    run(`git remote add origin ${remote}`)
  } catch {
    /* already set */
  }
}

run("git fetch origin")
run("git checkout main")
run("git reset --hard origin/main")
run("git clean -fd scripts backend/app/gateway.py")

const head = runCapture("git rev-parse --short HEAD")
const subject = runCapture("git log -1 --pretty=%s")
console.log(`HEAD ${head} — ${subject}`)

const checks = [
  "scripts/run-frontend.js",
  "scripts/wait-api.js",
  "scripts/run-api.js",
  "scripts/boot-api.py",
  "backend/app/gateway.py",
]
for (const rel of checks) {
  const full = path.join(root, rel)
  if (!fs.existsSync(full)) {
    console.error("MISSING after reset:", rel)
    process.exit(1)
  }
}

const rf = fs.readFileSync(path.join(root, "scripts/run-frontend.js"), "utf8")
if (!rf.includes(BUILD) || !rf.includes("Waiting for full API ready")) {
  console.error("run-frontend.js still STALE after git reset — file may be locked.")
  console.error("Stop StudioNels completely in Pinokio, close extra terminals, run Update again.")
  process.exit(1)
}

console.log(`update-ok: pull-main ${BUILD} @ ${head}`)

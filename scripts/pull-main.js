/**
 * Force this checkout onto origin/main and verify proxy8787 scripts landed.
 */
const { execSync } = require("child_process")
const fs = require("fs")
const path = require("path")

const BUILD = "2026-11-15-proxy8787"
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

const rf = fs.readFileSync(path.join(root, "scripts/run-api.js"), "utf8")
if (!rf.includes(BUILD) || !rf.includes("node-proxy")) {
  console.error("run-api.js still STALE after git reset.")
  console.error("Stop StudioNels completely, then Update again.")
  process.exit(1)
}

console.log(`update-ok: pull-main ${BUILD} @ ${head}`)

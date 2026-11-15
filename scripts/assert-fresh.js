/**
 * Fail Start/Update immediately if this checkout is stale.
 * The Vite 502 bug happens when an old run-frontend.js starts without waiting for :8787.
 */
const fs = require("fs")
const path = require("path")

const BUILD = "2026-11-15-no502"
const root = path.join(__dirname, "..")

const required = [
  ["scripts/run-frontend.js", BUILD],
  ["scripts/wait-api.js", BUILD],
  ["scripts/run-api.js", BUILD],
  ["scripts/boot-api.py", "boot-api: python alive"],
  ["backend/app/gateway.py", "Ultra-light ASGI"],
]

console.log(`assert-fresh build ${BUILD}`)

let bad = false
for (const [rel, needle] of required) {
  const full = path.join(root, rel)
  if (!fs.existsSync(full)) {
    console.error(`MISSING: ${rel}`)
    bad = true
    continue
  }
  const text = fs.readFileSync(full, "utf8")
  if (!text.includes(needle)) {
    console.error(`STALE: ${rel} (expected to contain ${JSON.stringify(needle)})`)
    bad = true
  } else {
    console.log(`ok: ${rel}`)
  }
}

if (bad) {
  console.error("")
  console.error("This StudioNels folder is OUT OF DATE.")
  console.error("In Pinokio: Stop → Update (wait for update-ok) → Start.")
  console.error("If Update fails, open a terminal in C:\\pinokio\\api\\studionels and run:")
  console.error("  git fetch origin")
  console.error("  git checkout main")
  console.error("  git reset --hard origin/main")
  process.exit(1)
}

console.log("assert-fresh: ok")

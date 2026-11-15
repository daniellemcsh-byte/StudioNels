/**
 * Fail Start/Update immediately if this checkout is stale.
 */
const fs = require("fs")
const path = require("path")

const BUILD = "2026-11-15-vitefix"
const root = path.join(__dirname, "..")

const required = [
  ["scripts/run-frontend.js", BUILD],
  ["scripts/run-frontend.js", "vite/bin/vite.js"],
  ["scripts/wait-api.js", "2026-11-15-detach"],
  ["scripts/run-api.js", "node-proxy"],
  ["scripts/run-api.js", "detached"],
  ["scripts/boot-api.py", "boot-api: python alive"],
  ["scripts/boot-api.py", "SetConsoleCtrlHandler"],
  ["backend/app/gateway.py", "Light ASGI entry"],
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
  process.exit(1)
}

console.log("assert-fresh: ok")

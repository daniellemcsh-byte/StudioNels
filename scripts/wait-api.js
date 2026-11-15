/**
 * Wait until TCP :8787 accepts connections.
 * Build stamp must appear in the Pinokio terminal — if you don't see it, Update failed.
 */
const fs = require("fs")
const net = require("net")
const path = require("path")

const BUILD = "2026-11-15-gateway"
const HOST = "127.0.0.1"
const PORT = 8787
// Soft cap: Start should not block the UI forever. Gateway binds in seconds;
// if it hasn't, fail with a clear message instead of spinning 10 minutes.
const MAX_MS = Number(process.env.STUDIONELS_WAIT_API_MS || 90000)
const EVERY_MS = 500
const root = path.join(__dirname, "..")
const cache = path.join(root, "cache")
const exitFile = path.join(cache, "api.exit")
const statusFile = path.join(cache, "api.status")
const started = Date.now()

function tcpOpen() {
  return new Promise((resolve) => {
    const sock = net.connect({ host: HOST, port: PORT }, () => {
      sock.end()
      resolve(true)
    })
    sock.on("error", () => resolve(false))
    sock.setTimeout(1500, () => {
      sock.destroy()
      resolve(false)
    })
  })
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"))
  } catch {
    return null
  }
}

;(async () => {
  console.log(`wait-api build ${BUILD}`)
  console.log(`Waiting for API port ${HOST}:${PORT} (TCP, not /api/health)`)
  console.log(`(up to ${Math.round(MAX_MS / 1000)}s — gateway should bind in a few seconds)`)
  console.log("Leave the run-api terminal alone. Do not CTRL+C that shell while it is starting.")
  console.log("If you do NOT see build 2026-11-15-gateway above, run Pinokio → Update first.")

  let lastLog = 0
  while (Date.now() - started < MAX_MS) {
    const dead = readJson(exitFile)
    if (dead) {
      console.error("")
      console.error(`API process exited before opening port ${PORT}.`)
      console.error(`Exit code: ${dead.code}${dead.signal ? ` signal=${dead.signal}` : ""}`)
      console.error("Open the Pinokio terminal that runs run-api.js and read the traceback.")
      console.error("Then try: Pinokio → Update → Install AMD engine → Stop → Start.")
      process.exit(1)
    }

    if (await tcpOpen()) {
      console.log(`OK: API is listening on http://${HOST}:${PORT}`)
      process.exit(0)
    }

    const elapsed = Date.now() - started
    if (elapsed - lastLog >= 5000) {
      lastLog = elapsed
      const st = readJson(statusFile)
      const state = st && st.state ? st.state : "unknown"
      const build = st && st.build ? st.build : "old-or-missing"
      console.log(`Still waiting… ${Math.round(elapsed / 1000)}s for ${HOST}:${PORT}`)
      console.log(`(run-api status: ${state}, build: ${build})`)
      if (st && st.lastLog) {
        console.log(`(last API log: ${String(st.lastLog).slice(0, 160)})`)
      } else {
        console.log("(no API log yet — open the run-api terminal; python may be hung before boot-api)")
      }
      if (build !== BUILD) {
        console.log("WARNING: run-api build mismatch — Pinokio → Stop → Update → Start.")
      }
    }
    await new Promise((r) => setTimeout(r, EVERY_MS))
  }

  console.error("")
  console.error(`Nothing is listening on ${HOST}:${PORT} after ${Math.round(MAX_MS / 1000)}s.`)
  const st = readJson(statusFile)
  if (st) console.error("Last status:", JSON.stringify(st, null, 2))
  console.error("Open the run-api terminal and paste everything from it.")
  console.error("Then: Pinokio → Update → Stop → Start.")
  // Non-zero so Pinokio shows failure instead of opening a half-dead UI silently.
  process.exit(1)
})()

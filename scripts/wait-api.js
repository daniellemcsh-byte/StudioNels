/**
 * Wait until TCP :8787 accepts connections.
 * Avoids /api/health — that endpoint probes Ollama and can hang, which made
 * Pinokio flash forever even when uvicorn was already running.
 *
 * Also watches cache/api.exit — if run-api died, fail immediately with a clear
 * message instead of spinning for minutes.
 *
 * Default timeout is 10 minutes: first Windows AMD/ROCm torch import can take
 * several minutes before uvicorn prints "Uvicorn running on".
 */
const fs = require("fs")
const net = require("net")
const path = require("path")

const HOST = "127.0.0.1"
const PORT = 8787
const MAX_MS = Number(process.env.STUDIONELS_WAIT_API_MS || 600000)
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
  console.log(`Waiting for API port ${HOST}:${PORT} (TCP, not /api/health)`)
  console.log(
    `(up to ${Math.round(MAX_MS / 1000)}s — first Windows ROCm import can take several minutes)`,
  )
  console.log(
    `Leave the run-api terminal alone. Do not CTRL+C that shell while it is starting.`,
  )
  let lastLog = 0
  while (Date.now() - started < MAX_MS) {
    const dead = readJson(exitFile)
    if (dead) {
      console.error("")
      console.error(`API process exited before opening port ${PORT}.`)
      console.error(`Exit code: ${dead.code}${dead.signal ? ` signal=${dead.signal}` : ""}`)
      console.error("Open the Pinokio terminal that runs run-api.js and read the traceback.")
      console.error("Then try: Pinokio → Update → Install AMD engine → Stop → Start.")
      console.error("Or: node scripts\\check-backend.js")
      process.exit(1)
    }

    if (await tcpOpen()) {
      console.log(`OK: API is listening on http://${HOST}:${PORT}`)
      process.exit(0)
    }

    const elapsed = Date.now() - started
    if (elapsed - lastLog >= 8000) {
      lastLog = elapsed
      const st = readJson(statusFile)
      const state = st && st.state ? st.state : "unknown"
      console.log(`Still waiting… ${Math.round(elapsed / 1000)}s for ${HOST}:${PORT}`)
      console.log(
        `If another Pinokio terminal shows “Uvicorn running”, the API is up — do not CTRL+C that shell.`,
      )
      if (state === "starting" || state === "spawned" || state === "loading") {
        console.log(
          `(run-api status: ${state} — waiting for uvicorn to bind; full API may still be loading)`,
        )
      }
      if (st && st.lastLog) {
        console.log(`(last API log: ${String(st.lastLog).slice(0, 160)})`)
      }
    }
    await new Promise((r) => setTimeout(r, EVERY_MS))
  }
  console.error("")
  console.error(`Nothing is listening on ${HOST}:${PORT} after ${Math.round(MAX_MS / 1000)}s.`)
  console.error(`Open the run-api terminal in Pinokio and paste any errors from there.`)
  console.error(`Then try: node scripts\\check-backend.js`)
  console.error("")
  process.exit(1)
})()

/**
 * Wait until TCP :8787 accepts connections.
 * Avoids /api/health — that endpoint probes Ollama and can hang, which made
 * Pinokio flash forever even when uvicorn was already running.
 *
 * Default timeout is 10 minutes: first Windows AMD/ROCm torch import can take
 * several minutes before uvicorn prints "Uvicorn running on".
 */
const net = require("net")

const HOST = "127.0.0.1"
const PORT = 8787
const MAX_MS = Number(process.env.STUDIONELS_WAIT_API_MS || 600000)
const EVERY_MS = 500
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
    if (await tcpOpen()) {
      console.log(`OK: API is listening on http://${HOST}:${PORT}`)
      process.exit(0)
    }
    const elapsed = Date.now() - started
    if (elapsed - lastLog >= 8000) {
      lastLog = elapsed
      console.log(`Still waiting… ${Math.round(elapsed / 1000)}s for ${HOST}:${PORT}`)
      console.log(
        `If another Pinokio terminal shows “Uvicorn running”, the API is up — do not CTRL+C that shell.`,
      )
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

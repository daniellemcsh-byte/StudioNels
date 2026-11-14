/**
 * Wait until TCP :8787 accepts connections.
 * Avoids /api/health — that endpoint probes Ollama and can hang, which made
 * Pinokio flash forever even when uvicorn was already running.
 */
const net = require("net")

const HOST = "127.0.0.1"
const PORT = 8787
const MAX_MS = Number(process.env.STUDIONELS_WAIT_API_MS || 180000)
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
  console.log(`(up to ${Math.round(MAX_MS / 1000)}s — first ROCm load can be slow)`)
  let lastLog = 0
  while (Date.now() - started < MAX_MS) {
    if (await tcpOpen()) {
      console.log(`API is listening on http://${HOST}:${PORT}`)
      process.exit(0)
    }
    const elapsed = Date.now() - started
    if (elapsed - lastLog >= 8000) {
      lastLog = elapsed
      console.log(`Still waiting… ${Math.round(elapsed / 1000)}s`)
    }
    await new Promise((r) => setTimeout(r, EVERY_MS))
  }
  console.error(
    `Nothing is listening on ${HOST}:${PORT}. Open the run-api Terminal in Pinokio.\n` +
      `Or run: node scripts\\check-backend.js`,
  )
  process.exit(1)
})()

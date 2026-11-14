/**
 * Block until StudioNels API answers (or fail with a clear message).
 * Uses /api/ready (instant) — NOT /api/health, which probes Ollama and can hang
 * long enough that Pinokio's waiter never succeeds and the UI keeps flashing.
 */
const http = require("http")

const URLS = [
  "http://127.0.0.1:8787/api/ready",
  "http://127.0.0.1:8787/api/health", // fallback for older backends
]
const MAX_MS = Number(process.env.STUDIONELS_WAIT_API_MS || 180000)
const EVERY_MS = 750
const REQ_TIMEOUT_MS = 8000
const started = Date.now()

function once(url) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: REQ_TIMEOUT_MS }, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on("error", () => resolve(false))
    req.on("timeout", () => {
      req.destroy()
      resolve(false)
    })
  })
}

async function anyReady() {
  for (const url of URLS) {
    if (await once(url)) return url
  }
  return null
}

;(async () => {
  console.log("Waiting for API ready on http://127.0.0.1:8787")
  console.log(`(up to ${Math.round(MAX_MS / 1000)}s — ROCm first load can be slow)`)
  let lastLog = 0
  while (Date.now() - started < MAX_MS) {
    const hit = await anyReady()
    if (hit) {
      console.log("API is up —", hit)
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
    "API did not become ready on port 8787. Open the run-api Terminal in Pinokio. " +
      "If uvicorn is already running, Stop → Start again after Update.",
  )
  process.exit(1)
})()

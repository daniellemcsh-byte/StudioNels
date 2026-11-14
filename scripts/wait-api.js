/**
 * Block until StudioNels API answers on 8787 (or fail with a clear message).
 * ROCm / first torch import on Windows can take 1–2+ minutes after Start.
 */
const http = require("http")

const URL = "http://127.0.0.1:8787/api/health"
const MAX_MS = Number(process.env.STUDIONELS_WAIT_API_MS || 180000)
const EVERY_MS = 1000
const started = Date.now()

function once() {
  return new Promise((resolve) => {
    const req = http.get(URL, { timeout: 2500 }, (res) => {
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

;(async () => {
  console.log("Waiting for API", URL)
  console.log(`(up to ${Math.round(MAX_MS / 1000)}s — ROCm torch can be slow the first time)`)
  let lastLog = 0
  while (Date.now() - started < MAX_MS) {
    if (await once()) {
      console.log("API is up on http://127.0.0.1:8787")
      process.exit(0)
    }
    const elapsed = Date.now() - started
    if (elapsed - lastLog >= 10000) {
      lastLog = elapsed
      console.log(`Still waiting… ${Math.round(elapsed / 1000)}s`)
    }
    await new Promise((r) => setTimeout(r, EVERY_MS))
  }
  console.error(
    "API did not start on port 8787 within " +
      Math.round(MAX_MS / 1000) +
      "s. Open the API Terminal in Pinokio (run-api.js). " +
      "If it is still loading torch, wait and Start again. " +
      "If it crashed, run: node scripts\\check-backend.js",
  )
  process.exit(1)
})()

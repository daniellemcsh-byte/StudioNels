/**
 * Block until StudioNels API answers on 8787 (or fail with a clear message).
 */
const http = require("http")

const URL = "http://127.0.0.1:8787/api/health"
const MAX_MS = 90000
const EVERY_MS = 500
const started = Date.now()

function once() {
  return new Promise((resolve) => {
    const req = http.get(URL, { timeout: 2000 }, (res) => {
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
  while (Date.now() - started < MAX_MS) {
    if (await once()) {
      console.log("API is up on http://127.0.0.1:8787")
      process.exit(0)
    }
    await new Promise((r) => setTimeout(r, EVERY_MS))
  }
  console.error(
    "API did not start on port 8787. Open Terminal in Pinokio and check the API log. " +
      "Try Install again if backend/.venv is missing.",
  )
  process.exit(1)
})()

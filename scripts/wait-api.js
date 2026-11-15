/**
 * Wait until http://127.0.0.1:8787/api/ready reports ready:true.
 * Node proxy binds immediately; Python on :8788 may take longer.
 */
const fs = require("fs")
const http = require("http")
const path = require("path")

const BUILD = "2026-11-15-detach"
const HOST = "127.0.0.1"
const PORT = 8787
const MAX_MS = Number(process.env.STUDIONELS_WAIT_API_MS || 300000)
const root = path.join(__dirname, "..")
const cache = path.join(root, "cache")
const exitFile = path.join(cache, "api.exit")
const statusFile = path.join(cache, "api.status")
const started = Date.now()

function httpReady() {
  return new Promise((resolve) => {
    const req = http.get({ host: HOST, port: PORT, path: "/api/ready", timeout: 2500 }, (res) => {
      let body = ""
      res.on("data", (c) => {
        body += c
      })
      res.on("end", () => {
        try {
          resolve({ statusCode: res.statusCode, ...(JSON.parse(body) || {}) })
        } catch {
          resolve({ statusCode: res.statusCode })
        }
      })
    })
    req.on("error", () => resolve(null))
    req.on("timeout", () => {
      req.destroy()
      resolve(null)
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
  console.log(`Waiting for full API ready at http://${HOST}:${PORT}/api/ready`)
  console.log(`(up to ${Math.round(MAX_MS / 1000)}s — python import on Windows can be slow)`)
  console.log("Watch the run-api terminal for boot-api / gateway lines.")

  let lastLog = 0
  while (Date.now() - started < MAX_MS) {
    const dead = readJson(exitFile)
    const st = readJson(statusFile)
    // Python exit is fatal only if proxy also gone; proxy stays up on purpose.
    if (dead && st && st.state === "exited") {
      console.error("")
      console.error(`Python API exited (code ${dead.code}) before ready.`)
      console.error("Open run-api and read the traceback.")
      process.exit(1)
    }

    const ready = await httpReady()
    if (ready && ready.ready) {
      console.log(`OK: full API ready on http://${HOST}:${PORT}`)
      process.exit(0)
    }

    const elapsed = Date.now() - started
    if (elapsed - lastLog >= 5000) {
      lastLog = elapsed
      const state = st && st.state ? st.state : "unknown"
      const build = st && st.build ? st.build : "old-or-missing"
      console.log(`Still waiting… ${Math.round(elapsed / 1000)}s`)
      console.log(
        `(proxy=${ready ? "up" : "down"}, ready=${!!(ready && ready.ready)}, ` +
          `status=${(ready && ready.status) || state}, build=${build})`,
      )
      if (ready && ready.lastLog) console.log(`(python: ${String(ready.lastLog).slice(0, 160)})`)
      else if (st && st.lastLog) console.log(`(last: ${String(st.lastLog).slice(0, 160)})`)
      else console.log("(no python log yet — run-api may still be importing uvicorn)")
      if (build !== BUILD) {
        console.log("WARNING: build mismatch — Stop → Update → Start.")
      }
    }
    await new Promise((r) => setTimeout(r, 500))
  }

  console.error("")
  console.error("Timed out waiting for full API ready.")
  console.error("Paste the run-api terminal output.")
  process.exit(1)
})()

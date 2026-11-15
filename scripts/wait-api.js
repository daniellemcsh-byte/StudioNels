/**
 * Wait until the API answers HTTP on :8787.
 * TCP alone is not enough — Vite 502 / ECONNREFUSED means nothing is listening.
 * Build stamp must appear — if missing, Pinokio Update did not land.
 */
const fs = require("fs")
const http = require("http")
const net = require("net")
const path = require("path")

const BUILD = "2026-11-15-no502"
const HOST = "127.0.0.1"
const PORT = 8787
// TCP+gateway should appear quickly; full app.main ready may take longer on Windows.
const MAX_MS = Number(process.env.STUDIONELS_WAIT_API_MS || 180000)
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

function httpReady() {
  return new Promise((resolve) => {
    const req = http.get(
      {
        host: HOST,
        port: PORT,
        path: "/api/ready",
        timeout: 2000,
      },
      (res) => {
        let body = ""
        res.on("data", (c) => {
          body += c
        })
        res.on("end", () => {
          let parsed = null
          try {
            parsed = JSON.parse(body)
          } catch {
            parsed = null
          }
          resolve({
            ok: res.statusCode === 200,
            statusCode: res.statusCode,
            ready: !!(parsed && parsed.ready),
            booting: !!(parsed && parsed.booting),
            body: parsed,
          })
        })
      },
    )
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
  console.log(`Waiting for API http://${HOST}:${PORT}/api/ready`)
  console.log(`(up to ${Math.round(MAX_MS / 1000)}s)`)
  console.log("If you do NOT see this build stamp, Pinokio → Update first.")

  let sawTcp = false
  let sawGateway = false
  let lastLog = 0
  while (Date.now() - started < MAX_MS) {
    const elapsed = Date.now() - started
    const dead = readJson(exitFile)
    if (dead) {
      console.error("")
      console.error(`API process exited before becoming ready (code ${dead.code}).`)
      console.error("Open the run-api terminal and read the Python traceback.")
      console.error("Then: Pinokio → Update → Stop → Start.")
      process.exit(1)
    }

    const tcp = await tcpOpen()
    if (tcp) sawTcp = true

    if (tcp) {
      const ready = await httpReady()
      if (ready && ready.ok && ready.ready) {
        console.log(`OK: full API ready on http://${HOST}:${PORT}`)
        process.exit(0)
      }
      if (ready && ready.ok) {
        sawGateway = true
      }
    }

    if (elapsed - lastLog >= 5000) {
      lastLog = elapsed
      const st = readJson(statusFile)
      const state = st && st.state ? st.state : "unknown"
      const build = st && st.build ? st.build : "old-or-missing"
      console.log(`Still waiting… ${Math.round(elapsed / 1000)}s`)
      console.log(
        `(tcp=${sawTcp ? "open" : "closed"}, gateway=${sawGateway ? "up" : "no"}, ` +
          `full_app=${sawGateway ? "loading…" : "waiting"}, run-api=${state}, build=${build})`,
      )
      if (st && st.lastLog) console.log(`(last API log: ${String(st.lastLog).slice(0, 160)})`)
      else console.log("(no API log yet — check the run-api terminal)")
      if (build !== BUILD) {
        console.log("WARNING: run-api build mismatch — Stop → Update → Start.")
      }
    }
    await new Promise((r) => setTimeout(r, EVERY_MS))
  }

  console.error("")
  console.error(`API never answered http://${HOST}:${PORT}/api/ready`)
  console.error("Vite would show 502 / ECONNREFUSED without this.")
  const st = readJson(statusFile)
  if (st) console.error("Last status:", JSON.stringify(st, null, 2))
  console.error("Open the run-api terminal and paste it here.")
  process.exit(1)
})()

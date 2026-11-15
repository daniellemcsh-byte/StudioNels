/**
 * Launch Vite only after the API answers on :8787.
 * Prevents the UI opening with proxy 502 / ECONNREFUSED when run-api never bound.
 */
const { spawn } = require("child_process")
const http = require("http")
const net = require("net")
const path = require("path")

const BUILD = "2026-11-15-no502"
const HOST = "127.0.0.1"
const PORT = 8787
const MAX_MS = Number(process.env.STUDIONELS_WAIT_API_MS || 180000)
const frontend = path.join(__dirname, "..", "frontend")

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

function httpReadyFull() {
  return new Promise((resolve) => {
    const req = http.get({ host: HOST, port: PORT, path: "/api/ready", timeout: 2000 }, (res) => {
      let body = ""
      res.on("data", (c) => {
        body += c
      })
      res.on("end", () => {
        try {
          const j = JSON.parse(body)
          resolve(res.statusCode === 200 && !!j.ready)
        } catch {
          resolve(false)
        }
      })
    })
    req.on("error", () => resolve(false))
    req.on("timeout", () => {
      req.destroy()
      resolve(false)
    })
  })
}

async function waitForApi() {
  console.log(`run-frontend build ${BUILD}`)
  console.log(`Waiting for full API ready on http://${HOST}:${PORT}/api/ready before Vite…`)
  const started = Date.now()
  let last = 0
  while (Date.now() - started < MAX_MS) {
    if ((await tcpOpen()) && (await httpReadyFull())) {
      console.log("API is fully ready — starting Vite.")
      return
    }
    const elapsed = Date.now() - started
    if (elapsed - last >= 5000) {
      last = elapsed
      console.log(`Still waiting for API… ${Math.round(elapsed / 1000)}s (Vite not started yet)`)
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  console.error("")
  console.error(`API not ready at http://${HOST}:${PORT} — refusing to start Vite.`)
  console.error("That is what caused 502 / ECONNREFUSED in the browser.")
  console.error("Open the run-api terminal, then: Pinokio → Update → Stop → Start.")
  process.exit(1)
}

;(async () => {
  await waitForApi()

  const env = {
    ...process.env,
    __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS: ".ts.net",
  }

  const npm = process.platform === "win32" ? "npm.cmd" : "npm"
  console.log("Starting Vite on 0.0.0.0:5173 (Tailscale / LAN OK)")

  const child = spawn(
    npm,
    ["run", "dev", "--", "--host", "0.0.0.0", "--port", "5173", "--strictPort"],
    {
      cwd: frontend,
      env,
      stdio: "inherit",
      windowsHide: true,
      shell: process.platform === "win32",
    },
  )

  child.on("exit", (code, signal) => {
    console.error("Vite exited", { code, signal })
    process.exit(code || 1)
  })
})().catch((err) => {
  console.error(err)
  process.exit(1)
})

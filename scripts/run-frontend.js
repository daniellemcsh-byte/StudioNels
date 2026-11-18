/**
 * Launch Vite only after http://127.0.0.1:8787/api/ready reports ready:true.
 *
 * On Windows, never spawn npm.cmd with shell:false — that throws spawn EINVAL.
 * Start Vite via `node node_modules/vite/bin/vite.js` instead.
 */
const { spawn } = require("child_process")
const fs = require("fs")
const http = require("http")
const path = require("path")

const BUILD = "2026-11-18-idlegpu"
const HOST = "127.0.0.1"
const PORT = 8787
const MAX_MS = Number(process.env.STUDIONELS_WAIT_API_MS || 300000)
const root = path.join(__dirname, "..")
const frontend = path.join(root, "frontend")
const statusFile = path.join(root, "cache", "api.status")
const viteJs = path.join(frontend, "node_modules", "vite", "bin", "vite.js")

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
          resolve(null)
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

function readStatus() {
  try {
    return JSON.parse(fs.readFileSync(statusFile, "utf8"))
  } catch {
    return null
  }
}

async function waitForApi() {
  console.log(`run-frontend build ${BUILD}`)
  console.log(`Waiting for full API ready on http://${HOST}:${PORT}/api/ready before Vite…`)
  console.log("If this sits here, open the run-api terminal — that is where Python boots.")
  const started = Date.now()
  let last = 0
  while (Date.now() - started < MAX_MS) {
    const ready = await httpReady()
    if (ready && ready.ready) {
      console.log("API is fully ready — starting Vite.")
      return
    }
    const elapsed = Date.now() - started
    if (elapsed - last >= 5000) {
      last = elapsed
      const st = readStatus()
      console.log(`Still waiting for API… ${Math.round(elapsed / 1000)}s (Vite not started yet)`)
      console.log(
        `(proxy=${ready ? "up" : "down"}, status=${(ready && ready.status) || (st && st.state) || "?"})`,
      )
      const log = (ready && ready.lastLog) || (st && st.lastLog)
      if (log) console.log(`(python: ${String(log).slice(0, 160)})`)
      else console.log("(no python log yet — check run-api for boot-api / errors)")
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  console.error("")
  console.error("API not ready — refusing to start Vite (avoids 502).")
  console.error("Paste the run-api terminal.")
  process.exit(1)
}

function startVite() {
  const env = {
    ...process.env,
    __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS: ".ts.net",
  }

  if (!fs.existsSync(viteJs)) {
    console.error("Missing", viteJs)
    console.error("Pinokio → Update (runs npm install in frontend), then Start again.")
    process.exit(1)
  }

  console.log("Starting Vite on 0.0.0.0:5173 (Tailscale / LAN OK)")
  console.log("Using", process.execPath, viteJs)

  // Spawn node + vite.js — works on Windows without npm.cmd / shell.
  const child = spawn(
    process.execPath,
    [viteJs, "--host", "0.0.0.0", "--port", "5173", "--strictPort"],
    {
      cwd: frontend,
      env,
      stdio: "inherit",
      windowsHide: true,
      shell: false,
    },
  )

  child.on("error", (err) => {
    console.error("Failed to start Vite:", err)
    process.exit(1)
  })

  child.on("exit", (code, signal) => {
    console.error("Vite exited", { code, signal })
    process.exit(code || 1)
  })
}

;(async () => {
  await waitForApi()
  startVite()
})().catch((err) => {
  console.error(err)
  process.exit(1)
})

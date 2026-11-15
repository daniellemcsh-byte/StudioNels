/**
 * Node owns :8787 immediately; Python gateway runs on :8788.
 * Python is spawned detached on Windows (avoids Pinokio CTRL+C killing uvicorn).
 * Writes cache/api.log and restarts Python a few times if it dies during boot.
 */
const { spawn } = require("child_process")
const fs = require("fs")
const http = require("http")
const path = require("path")
const { assertVenv, cleanEnv } = require("./venv-env")

const BUILD = "2026-11-15-detach"
const PUBLIC_HOST = "127.0.0.1"
const PUBLIC_PORT = 8787
const PY_PORT = 8788
const MAX_PY_RESTARTS = 5

const root = path.join(__dirname, "..")
const backend = path.join(root, "backend")
const cache = path.join(root, "cache")
const bootPy = path.join(root, "scripts", "boot-api.py")

fs.mkdirSync(cache, { recursive: true })
const pidFile = path.join(cache, "api.pid")
const statusFile = path.join(cache, "api.status")
const exitFile = path.join(cache, "api.exit")
const logFile = path.join(cache, "api.log")

let pyReady = false
let pyBooting = true
let lastPyLog = ""
let recentLogs = []
let child = null
let pyRestarts = 0
let stopping = false

function writeStatus(obj) {
  try {
    fs.writeFileSync(
      statusFile,
      JSON.stringify(
        {
          build: BUILD,
          recentLogs: recentLogs.slice(-12),
          ...obj,
          ts: Date.now(),
        },
        null,
        2,
      ),
    )
  } catch {
    /* ignore */
  }
}

function appendLog(text) {
  try {
    fs.appendFileSync(logFile, text)
  } catch {
    /* ignore */
  }
  for (const line of text.split(/\r?\n/)) {
    const t = line.trim()
    if (!t) continue
    lastPyLog = t.slice(0, 400)
    recentLogs.push(t.slice(0, 400))
    if (recentLogs.length > 80) recentLogs = recentLogs.slice(-80)
  }
}

try {
  fs.unlinkSync(exitFile)
} catch {
  /* ignore */
}
try {
  fs.writeFileSync(logFile, `--- run-api ${BUILD} ${new Date().toISOString()} ---\n`)
} catch {
  /* ignore */
}

function proxyReq(clientReq, clientRes) {
  const opts = {
    hostname: "127.0.0.1",
    port: PY_PORT,
    path: clientReq.url,
    method: clientReq.method,
    headers: { ...clientReq.headers, host: `127.0.0.1:${PY_PORT}` },
    timeout: 600000,
  }
  const upstream = http.request(opts, (upRes) => {
    clientRes.writeHead(upRes.statusCode || 502, upRes.headers)
    upRes.pipe(clientRes)
  })
  upstream.on("error", () => {
    if (!clientRes.headersSent) {
      const body = JSON.stringify({
        ok: false,
        ready: false,
        booting: pyBooting,
        status: pyBooting ? "waiting_for_python" : "python_down",
        detail: "Python API not reachable on :8788 — see run-api terminal / cache/api.log",
        lastLog: lastPyLog || null,
        recentLogs: recentLogs.slice(-8),
      })
      clientRes.writeHead(503, {
        "content-type": "application/json",
        "cache-control": "no-store",
      })
      clientRes.end(body)
    }
  })
  clientReq.pipe(upstream)
}

function readyPayload() {
  return {
    ok: true,
    ready: pyReady,
    booting: !pyReady && pyBooting,
    status: pyReady ? "ready" : pyBooting ? "waiting_for_python" : "python_down",
    proxy: true,
    build: BUILD,
    python_port: PY_PORT,
    lastLog: lastPyLog || null,
    recentLogs: recentLogs.slice(-8),
    restarts: pyRestarts,
  }
}

const server = http.createServer((req, res) => {
  const url = req.url || "/"
  if (url === "/api/ready" || url === "/api/ready/") {
    if (!pyReady) {
      const body = JSON.stringify(readyPayload())
      res.writeHead(200, {
        "content-type": "application/json",
        "cache-control": "no-store",
      })
      res.end(body)
      return
    }
  }
  proxyReq(req, res)
})

console.log(`run-api build ${BUILD}`)
writeStatus({ state: "starting", pid: process.pid })

server.listen(PUBLIC_PORT, PUBLIC_HOST, () => {
  console.log(`node-proxy: bound ${PUBLIC_HOST}:${PUBLIC_PORT}`)
  console.log(`node-proxy: will forward to python :${PY_PORT}`)
  writeStatus({ state: "proxy_listening", pid: process.pid })
  try {
    startPython()
  } catch (err) {
    console.error(err)
    pyBooting = false
    lastPyLog = String(err && err.message ? err.message : err)
    writeStatus({ state: "exited", code: 1, lastLog: lastPyLog })
  }
})

server.on("error", (err) => {
  console.error("node-proxy failed to bind :8787", err)
  writeStatus({ state: "exited", code: 1, lastLog: String(err) })
  process.exit(1)
})

function pollPythonReady() {
  const req = http.get(
    { host: "127.0.0.1", port: PY_PORT, path: "/api/ready", timeout: 2000 },
    (res) => {
      let body = ""
      res.on("data", (c) => {
        body += c
      })
      res.on("end", () => {
        try {
          const j = JSON.parse(body)
          if (res.statusCode === 200 && j.ready) {
            if (!pyReady) {
              console.log("node-proxy: python full API ready — proxying :8787 → :8788")
            }
            pyReady = true
            pyBooting = false
            writeStatus({
              state: "api_ready",
              pid: child && child.pid,
              lastLog: lastPyLog,
            })
          } else if (res.statusCode === 200) {
            pyBooting = true
            writeStatus({
              state: "python_booting",
              pid: child && child.pid,
              lastLog: lastPyLog || "gateway up, app.main loading",
            })
          }
        } catch {
          /* ignore */
        }
        setTimeout(pollPythonReady, pyReady ? 5000 : 1000)
      })
    },
  )
  req.on("error", () => {
    pyReady = false
    setTimeout(pollPythonReady, 1000)
  })
  req.on("timeout", () => {
    req.destroy()
    setTimeout(pollPythonReady, 1000)
  })
}

function startPython() {
  const pyPath = assertVenv(root)
  const env = {
    ...cleanEnv(pyPath),
    STUDIONELS_API_PORT: String(PY_PORT),
    STUDIONELS_API_HOST: "127.0.0.1",
  }

  console.log("Using", pyPath)
  if (!fs.existsSync(bootPy)) {
    throw new Error(`Missing ${bootPy}`)
  }

  console.log(
    `Starting boot-api (python) on 127.0.0.1:${PY_PORT} (attempt ${pyRestarts + 1}/${MAX_PY_RESTARTS + 1}) …`,
  )

  // Detach on Windows so Pinokio/Node console CTRL+C does not kill uvicorn
  // right after "gateway: app.main ready" (exit code 0 + "Shutting down").
  const childOpts = {
    cwd: backend,
    env,
    windowsHide: true,
    // ignore stdin; detached process must not share the Pinokio console group.
    stdio: ["ignore", "pipe", "pipe"],
  }
  if (process.platform === "win32") {
    childOpts.detached = true
    // CREATE_NEW_PROCESS_GROUP (0x00000200) — CTRL+C to Pinokio won't hit Python.
    childOpts.windowsVerbatimArguments = false
    childOpts.shell = false
  }
  child = spawn(pyPath, ["-u", bootPy], childOpts)

  try {
    fs.writeFileSync(pidFile, String(child.pid || ""))
  } catch {
    /* ignore */
  }
  writeStatus({ state: "python_spawned", pid: child.pid, python: pyPath })

  function onChunk(buf, stream) {
    const text = buf.toString("utf8")
    stream.write(buf)
    appendLog(text)
    writeStatus({
      state: /Uvicorn running/i.test(lastPyLog)
        ? "python_listening"
        : /gateway:\s*ready/i.test(lastPyLog)
          ? "api_ready"
          : /boot-api:|gateway:/i.test(lastPyLog)
            ? "python_loading"
            : "python_spawned",
      pid: child.pid,
      lastLog: lastPyLog,
    })
  }

  child.stdout.on("data", (buf) => onChunk(buf, process.stdout))
  child.stderr.on("data", (buf) => onChunk(buf, process.stderr))

  child.on("error", (err) => {
    console.error("Failed to spawn API python:", err)
    pyBooting = false
    lastPyLog = String(err)
    appendLog(`\nSPAWN ERROR: ${err}\n`)
    writeStatus({ state: "exited", code: 1, lastLog: lastPyLog })
  })

  child.on("exit", (code, signal) => {
    const payload = { code: code == null ? 1 : code, signal: signal || null, ts: Date.now() }
    pyReady = false
    appendLog(`\n--- python exited ${JSON.stringify(payload)} ---\n`)
    console.error("")
    console.error("API python exited", payload)
    console.error("Recent python log:")
    for (const line of recentLogs.slice(-20)) console.error(" ", line)
    console.error("Full log:", logFile)

    try {
      fs.writeFileSync(exitFile, JSON.stringify({ ...payload, recentLogs: recentLogs.slice(-30) }, null, 2))
    } catch {
      /* ignore */
    }

    if (!stopping && !pyReady && pyRestarts < MAX_PY_RESTARTS) {
      pyRestarts += 1
      pyBooting = true
      writeStatus({ state: "python_restarting", ...payload, lastLog: lastPyLog })
      console.error(`Restarting python in 2s (attempt ${pyRestarts + 1})…`)
      setTimeout(() => {
        try {
          startPython()
        } catch (err) {
          console.error(err)
        }
      }, 2000)
      return
    }

    pyBooting = false
    writeStatus({ state: "exited", ...payload, lastLog: lastPyLog })
  })

  if (pyRestarts === 0) pollPythonReady()
}

function killPython() {
  if (!child || !child.pid) return
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
        windowsHide: true,
      })
    } else {
      child.kill("SIGTERM")
    }
  } catch {
    /* ignore */
  }
}

process.on("SIGINT", () => {
  stopping = true
  killPython()
  process.exit(0)
})
process.on("SIGTERM", () => {
  stopping = true
  killPython()
  process.exit(0)
})


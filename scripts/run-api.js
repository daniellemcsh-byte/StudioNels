/**
 * Node owns :8787 immediately (so Start/Vite never see ECONNREFUSED), then
 * spawns Python gateway on :8788 and reverse-proxies once it answers.
 */
const { spawn } = require("child_process")
const fs = require("fs")
const http = require("http")
const path = require("path")
const { assertVenv, cleanEnv } = require("./venv-env")

const BUILD = "2026-11-15-proxy8787"
const PUBLIC_HOST = "127.0.0.1"
const PUBLIC_PORT = 8787
const PY_PORT = 8788

const root = path.join(__dirname, "..")
const backend = path.join(root, "backend")
const cache = path.join(root, "cache")
const bootPy = path.join(root, "scripts", "boot-api.py")

fs.mkdirSync(cache, { recursive: true })
const pidFile = path.join(cache, "api.pid")
const statusFile = path.join(cache, "api.status")
const exitFile = path.join(cache, "api.exit")

let pyReady = false
let pyBooting = true
let lastPyLog = ""
let child = null
let pyPath = ""

function writeStatus(obj) {
  try {
    fs.writeFileSync(
      statusFile,
      JSON.stringify({ build: BUILD, ...obj, ts: Date.now() }, null, 2),
    )
  } catch {
    /* ignore */
  }
}

try {
  fs.unlinkSync(exitFile)
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
        detail: "Python API not reachable on :8788 — see run-api terminal.",
        lastLog: lastPyLog || null,
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
  pyPath = assertVenv(root)
  const env = {
    ...cleanEnv(pyPath),
    STUDIONELS_API_PORT: String(PY_PORT),
    STUDIONELS_API_HOST: "127.0.0.1",
  }

  console.log("Using", pyPath)
  if (!fs.existsSync(bootPy)) {
    throw new Error(`Missing ${bootPy}`)
  }

  console.log("Starting boot-api (python) on 127.0.0.1:8788 …")
  console.log("(First Windows import of uvicorn can take a while — leave this terminal alone.)")

  child = spawn(pyPath, ["-u", bootPy], {
    cwd: backend,
    stdio: ["ignore", "pipe", "pipe"],
    env,
    windowsHide: true,
  })

  try {
    fs.writeFileSync(pidFile, String(child.pid || ""))
  } catch {
    /* ignore */
  }
  writeStatus({ state: "python_spawned", pid: child.pid, python: pyPath })

  function onChunk(buf, stream) {
    const text = buf.toString("utf8")
    stream.write(buf)
    const line = text.trim().split(/\r?\n/).filter(Boolean).pop()
    if (!line) return
    lastPyLog = line.slice(0, 300)
    let state = "python_spawned"
    if (/Uvicorn running/i.test(line)) state = "python_listening"
    else if (/gateway:\s*ready/i.test(line)) state = "api_ready"
    else if (/boot-api:|gateway:/i.test(line)) state = "python_loading"
    writeStatus({ state, pid: child.pid, lastLog: lastPyLog })
  }

  child.stdout.on("data", (buf) => onChunk(buf, process.stdout))
  child.stderr.on("data", (buf) => onChunk(buf, process.stderr))

  child.on("error", (err) => {
    console.error("Failed to spawn API python:", err)
    pyBooting = false
    lastPyLog = String(err)
    writeStatus({ state: "exited", code: 1, lastLog: lastPyLog })
    try {
      fs.writeFileSync(
        exitFile,
        JSON.stringify({ code: 1, signal: null, ts: Date.now(), error: String(err) }, null, 2),
      )
    } catch {
      /* ignore */
    }
  })

  child.on("exit", (code, signal) => {
    const payload = { code: code == null ? 1 : code, signal: signal || null, ts: Date.now() }
    pyReady = false
    pyBooting = false
    try {
      fs.writeFileSync(exitFile, JSON.stringify(payload, null, 2))
    } catch {
      /* ignore */
    }
    writeStatus({ state: "exited", ...payload, lastLog: lastPyLog })
    console.error("")
    console.error("API python exited", payload)
    console.error("Scroll up for the traceback.")
  })

  pollPythonReady()
}

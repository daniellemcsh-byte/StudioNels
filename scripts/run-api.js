/**
 * Supervise the StudioNels API on 127.0.0.1:8787.
 *
 * Python binds the port itself (no Node proxy, no :8788). An open stdin pipe
 * stops uvicorn treating EOF as "shut down", and a new Windows process group
 * keeps Pinokio CTRL+C off this process. If Python still exits, it is restarted.
 */
const { spawn } = require("child_process")
const fs = require("fs")
const path = require("path")
const { assertVenv, cleanEnv } = require("./venv-env")

const BUILD = "2026-11-18-idlegpu"
const root = path.join(__dirname, "..")
const backend = path.join(root, "backend")
const cache = path.join(root, "cache")
const bootPy = path.join(root, "scripts", "boot-api.py")

fs.mkdirSync(cache, { recursive: true })
const pidFile = path.join(cache, "api.pid")
const statusFile = path.join(cache, "api.status")
const exitFile = path.join(cache, "api.exit")
const logFile = path.join(cache, "api.log")

let lastPyLog = ""
let recentLogs = []
let child = null
let pyRestarts = 0
let stopping = false

function writeStatus(obj) {
  try {
    fs.writeFileSync(
      statusFile,
      JSON.stringify({ build: BUILD, recentLogs: recentLogs.slice(-12), ...obj, ts: Date.now() }, null, 2),
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
  for (const line of String(text).split(/\r?\n/)) {
    const t = line.trim()
    if (!t) continue
    lastPyLog = t.slice(0, 400)
    recentLogs.push(lastPyLog)
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

console.log(`run-api build ${BUILD}`)
console.log("API will listen on http://127.0.0.1:8787 (python, no proxy)")
writeStatus({ state: "starting", pid: process.pid })

function startPython() {
  const pyPath = assertVenv(root)
  const env = {
    ...cleanEnv(pyPath),
    STUDIONELS_API_PORT: "8787",
    STUDIONELS_API_HOST: "127.0.0.1",
  }
  if (!fs.existsSync(bootPy)) {
    console.error("Missing", bootPy)
    process.exit(1)
  }

  console.log(`Using ${pyPath}`)
  console.log(`Starting boot-api on 127.0.0.1:8787 (start ${pyRestarts + 1}) …`)

  const childOpts = {
    cwd: backend,
    env,
    // windowsHide + no detached: detached opens a new console on Windows,
    // which is the backend window that kept popping up on every restart.
    windowsHide: true,
    shell: false,
    // Open stdin pipe: closing stdin makes uvicorn exit on Windows.
    stdio: ["pipe", "pipe", "pipe"],
  }
  child = spawn(pyPath, ["-u", bootPy], childOpts)
  if (child.stdin) child.stdin.unref?.()

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
    let state = "python_spawned"
    if (/Uvicorn running/i.test(lastPyLog)) state = "listening"
    else if (/gateway:\s*ready/i.test(lastPyLog)) state = "api_ready"
    else if (/boot-api:|gateway:/i.test(lastPyLog)) state = "python_loading"
    writeStatus({ state, pid: child.pid, lastLog: lastPyLog })
  }

  child.stdout.on("data", (buf) => onChunk(buf, process.stdout))
  child.stderr.on("data", (buf) => onChunk(buf, process.stderr))
  child.on("error", (err) => {
    console.error("Failed to spawn API python:", err)
    appendLog(`\nSPAWN ERROR: ${err}\n`)
    writeStatus({ state: "exited", code: 1, lastLog: String(err) })
  })
  child.on("exit", (code, signal) => {
    const payload = { code: code == null ? 1 : code, signal: signal || null, ts: Date.now() }
    appendLog(`\n--- python exited ${JSON.stringify(payload)} ---\n`)
    console.error("API python exited", payload)
    try {
      fs.writeFileSync(exitFile, JSON.stringify({ ...payload, recentLogs: recentLogs.slice(-20) }, null, 2))
    } catch {
      /* ignore */
    }
    if (stopping) {
      writeStatus({ state: "exited", ...payload, lastLog: lastPyLog })
      return
    }
    pyRestarts += 1
    const wait = Math.min(8000, 1000 * pyRestarts)
    console.error(`Restarting API in ${wait}ms …`)
    writeStatus({ state: "python_restarting", ...payload, lastLog: lastPyLog })
    setTimeout(() => {
      try {
        startPython()
      } catch (err) {
        console.error(err)
      }
    }, wait)
  })
}

function killPython() {
  if (!child || !child.pid) return
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true })
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

startPython()

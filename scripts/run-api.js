/**
 * Start StudioNels FastAPI with the local venv python (Windows + Unix).
 *
 * Uses scripts/boot-api.py → app.gateway:app so:
 *  1) a log line prints before slow imports
 *  2) :8787 binds before the heavy app.main stack loads
 *
 * Writes cache/api.pid + cache/api.status for wait-api / diagnostics.
 */
const { spawn } = require("child_process")
const fs = require("fs")
const path = require("path")
const { assertVenv, cleanEnv } = require("./venv-env")

const BUILD = "2026-11-15-gateway"
const root = path.join(__dirname, "..")
const backend = path.join(root, "backend")
const cache = path.join(root, "cache")
const bootPy = path.join(root, "scripts", "boot-api.py")
const py = assertVenv(root)
const env = cleanEnv(py)

fs.mkdirSync(cache, { recursive: true })
const pidFile = path.join(cache, "api.pid")
const statusFile = path.join(cache, "api.status")
const exitFile = path.join(cache, "api.exit")

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

console.log(`run-api build ${BUILD}`)
console.log("Using", py)
console.log("Starting boot-api → gateway on 127.0.0.1:8787 …")
writeStatus({ state: "starting", pid: process.pid, python: py })

if (!fs.existsSync(bootPy)) {
  console.error("Missing", bootPy)
  console.error("Pinokio → Update (need latest main), then Stop → Start.")
  writeStatus({ state: "exited", code: 1 })
  process.exit(1)
}

const child = spawn(py, [bootPy], {
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
writeStatus({ state: "spawned", pid: child.pid, python: py })

function onChunk(buf, stream) {
  const text = buf.toString("utf8")
  stream.write(buf)
  const line = text.trim().split(/\r?\n/).filter(Boolean).pop()
  if (!line) return
  let state = "spawned"
  if (/Uvicorn running/i.test(line)) state = "listening"
  else if (/gateway:\s*ready/i.test(line)) state = "api_ready"
  else if (/boot-api:|gateway:/i.test(line)) state = "loading"
  writeStatus({
    state,
    pid: child.pid,
    lastLog: line.slice(0, 300),
  })
}

child.stdout.on("data", (buf) => onChunk(buf, process.stdout))
child.stderr.on("data", (buf) => onChunk(buf, process.stderr))

child.on("error", (err) => {
  console.error("Failed to spawn API python:", err)
  writeStatus({ state: "exited", code: 1, lastLog: String(err) })
  try {
    fs.writeFileSync(
      exitFile,
      JSON.stringify({ code: 1, signal: null, ts: Date.now(), error: String(err) }, null, 2),
    )
  } catch {
    /* ignore */
  }
  process.exit(1)
})

child.on("exit", (code, signal) => {
  const payload = { code: code == null ? 1 : code, signal: signal || null, ts: Date.now() }
  try {
    fs.writeFileSync(exitFile, JSON.stringify(payload, null, 2))
  } catch {
    /* ignore */
  }
  writeStatus({ state: "exited", ...payload })
  console.error("")
  console.error("API exited", payload)
  console.error("If this happened during Start, scroll up for the Python traceback.")
  console.error("Common fixes: Pinokio Update, Install AMD engine, then Stop → Start.")
  process.exit(code || 1)
})

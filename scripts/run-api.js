/**
 * Start StudioNels FastAPI with the local venv python (Windows + Unix).
 * Avoids Pinokio conda "python" shadowing the venv / breaking ROCm DLLs.
 *
 * Uses app.gateway:app so uvicorn binds :8787 immediately, then loads
 * app.main in a background thread (see backend/app/gateway.py).
 *
 * Writes cache/api.pid + cache/api.status so wait-api can detect a dead API
 * instead of spinning forever on :8787.
 */
const { spawn } = require("child_process")
const fs = require("fs")
const path = require("path")
const { assertVenv, cleanEnv } = require("./venv-env")

const root = path.join(__dirname, "..")
const backend = path.join(root, "backend")
const cache = path.join(root, "cache")
const py = assertVenv(root)
const env = cleanEnv(py)

fs.mkdirSync(cache, { recursive: true })
const pidFile = path.join(cache, "api.pid")
const statusFile = path.join(cache, "api.status")
const exitFile = path.join(cache, "api.exit")

function writeStatus(obj) {
  try {
    fs.writeFileSync(statusFile, JSON.stringify({ ...obj, ts: Date.now() }, null, 2))
  } catch {
    /* ignore */
  }
}

try {
  fs.unlinkSync(exitFile)
} catch {
  /* ignore */
}

console.log("Using", py)
console.log("Starting uvicorn gateway on 127.0.0.1:8787 …")
console.log("(Port opens immediately; full API loads in the background.)")
writeStatus({ state: "starting", pid: process.pid, python: py })

const child = spawn(
  py,
  [
    "-m",
    "uvicorn",
    "app.gateway:app",
    "--app-dir",
    ".",
    "--host",
    "127.0.0.1",
    "--port",
    "8787",
    "--log-level",
    "info",
  ],
  {
    cwd: backend,
    stdio: ["ignore", "pipe", "pipe"],
    env,
    windowsHide: true,
  },
)

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
  if (line) {
    writeStatus({
      state: /Uvicorn running/i.test(line)
        ? "listening"
        : /gateway:\s*ready/i.test(line)
          ? "api_ready"
          : /gateway:/i.test(line)
            ? "loading"
            : "spawned",
      pid: child.pid,
      lastLog: line.slice(0, 300),
    })
  }
}

child.stdout.on("data", (buf) => onChunk(buf, process.stdout))
child.stderr.on("data", (buf) => onChunk(buf, process.stderr))

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

/**
 * Start StudioNels FastAPI with the local venv python (Windows + Unix).
 * Avoids Pinokio conda "python" shadowing the venv.
 */
const { spawn } = require("child_process")
const fs = require("fs")
const path = require("path")

const root = path.join(__dirname, "..")
const backend = path.join(root, "backend")
const py =
  process.platform === "win32"
    ? path.join(backend, ".venv", "Scripts", "python.exe")
    : path.join(backend, ".venv", "bin", "python")

if (!fs.existsSync(py)) {
  console.error("Missing venv python at", py)
  console.error("In Pinokio: run Install again for StudioNels.")
  process.exit(1)
}

console.log("Using", py)
const child = spawn(
  py,
  [
    "-m",
    "uvicorn",
    "app.main:app",
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
    stdio: "inherit",
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    windowsHide: true,
  },
)

child.on("exit", (code, signal) => {
  console.error("API exited", { code, signal })
  process.exit(code || 1)
})

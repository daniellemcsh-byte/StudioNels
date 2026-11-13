/**
 * Fail fast if venv / uvicorn / app.main cannot import.
 */
const { spawnSync } = require("child_process")
const fs = require("fs")
const path = require("path")

const root = path.join(__dirname, "..")
const backend = path.join(root, "backend")
const py =
  process.platform === "win32"
    ? path.join(backend, ".venv", "Scripts", "python.exe")
    : path.join(backend, ".venv", "bin", "python")

if (!fs.existsSync(py)) {
  console.error("ERROR: backend/.venv not found.")
  console.error("Fix: Pinokio → StudioNels → Install")
  process.exit(1)
}

const probe = spawnSync(
  py,
  ["-c", "import uvicorn; import fastapi; import app.main; print('backend-ok')"],
  {
    cwd: backend,
    encoding: "utf8",
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    windowsHide: true,
  },
)

if (probe.status !== 0) {
  console.error("ERROR: backend import failed")
  console.error(probe.stdout || "")
  console.error(probe.stderr || "")
  console.error("Fix: Pinokio → StudioNels → Install (reinstalls requirements)")
  process.exit(1)
}

console.log(probe.stdout.trim() || "backend-ok")

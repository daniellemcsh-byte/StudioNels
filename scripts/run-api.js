/**
 * Start StudioNels FastAPI with the local venv python (Windows + Unix).
 * Avoids Pinokio conda "python" shadowing the venv / breaking ROCm DLLs.
 */
const { spawn } = require("child_process")
const path = require("path")
const { assertVenv, cleanEnv } = require("./venv-env")

const root = path.join(__dirname, "..")
const backend = path.join(root, "backend")
const py = assertVenv(root)
const env = cleanEnv(py)

console.log("Using", py)
console.log("Starting uvicorn on 127.0.0.1:8787 …")
console.log(
  "(First Windows ROCm import can take several minutes before “Uvicorn running” appears.)",
)
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
    env,
    windowsHide: true,
  },
)

child.on("exit", (code, signal) => {
  console.error("API exited", { code, signal })
  process.exit(code || 1)
})

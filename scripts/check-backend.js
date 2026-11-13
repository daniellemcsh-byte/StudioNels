/**
 * Fail fast if venv / uvicorn / app.main cannot import.
 * Prints a full traceback so Pinokio Terminal shows the real error.
 */
const { spawnSync } = require("child_process")
const path = require("path")
const { assertVenv, cleanEnv } = require("./venv-env")

const root = path.join(__dirname, "..")
const backend = path.join(root, "backend")
const py = assertVenv(root)
const env = cleanEnv(py)

console.log("Checking", py)

const steps = [
  ["import fastapi; print('fastapi-ok')", "fastapi"],
  ["import uvicorn; print('uvicorn-ok')", "uvicorn"],
  ["import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available()); print('torch-ok')", "torch"],
  ["import app.main; print('backend-ok')", "app.main"],
]

for (const [code, label] of steps) {
  const probe = spawnSync(py, ["-c", code], {
    cwd: backend,
    encoding: "utf8",
    env,
    windowsHide: true,
  })
  if (probe.stdout) process.stdout.write(probe.stdout)
  if (probe.status !== 0) {
    console.error("")
    console.error("ERROR: backend import failed at step:", label)
    if (probe.stderr) console.error(probe.stderr)
    if (probe.stdout) console.error(probe.stdout)
    console.error("")
    console.error("Try in PowerShell:")
    console.error(`  cd C:\\pinokio\\api\\studionels\\backend`)
    console.error(`  .\\.venv\\Scripts\\python.exe -c "import app.main"`)
    process.exit(1)
  }
}

console.log("backend-ok")

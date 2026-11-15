/**
 * Fail fast if venv / uvicorn / app.main cannot import.
 * Prints a full traceback so Pinokio Terminal shows the real error.
 *
 * torch is NOT required here: importing it on Windows AMD/ROCm can take minutes
 * and would double cold-start cost (check-backend then run-api). Generate needs
 * torch later; the API can still bind for the UI without it at Start time.
 * Set STUDIONELS_SKIP_TORCH_CHECK=0 to optionally probe torch (non-fatal).
 */
const { spawnSync } = require("child_process")
const path = require("path")
const { assertVenv, cleanEnv } = require("./venv-env")

const root = path.join(__dirname, "..")
const backend = path.join(root, "backend")
const py = assertVenv(root)
const env = cleanEnv(py)

console.log("check-backend build 2026-11-15-proxy8787")
console.log("Checking", py)

const steps = [
  ["import fastapi; print('fastapi-ok')", "fastapi"],
  ["import uvicorn; print('uvicorn-ok')", "uvicorn"],
  // Gateway must import instantly — boot-api loads this before binding :8787.
  ["import app.gateway; print('gateway-ok')", "app.gateway"],
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

// Optional non-fatal torch probe (skip by default — Start must stay fast).
const skipTorch =
  process.env.STUDIONELS_SKIP_TORCH_CHECK !== "0" &&
  process.env.STUDIONELS_SKIP_TORCH_CHECK !== "false"
if (skipTorch) {
  console.log("Skipping torch check (set STUDIONELS_SKIP_TORCH_CHECK=0 to probe)")
} else {
  console.log("Probing torch (non-fatal)…")
  const torchProbe = spawnSync(
    py,
    [
      "-c",
      "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available()); print('torch-ok')",
    ],
    {
      cwd: backend,
      encoding: "utf8",
      env,
      windowsHide: true,
      timeout: 30000,
    },
  )
  if (torchProbe.stdout) process.stdout.write(torchProbe.stdout)
  if (torchProbe.status !== 0 || torchProbe.error) {
    console.warn("WARN: torch import failed or timed out — API can still start for UI.")
    console.warn("Generate needs torch later. Fix GPU/ROCm install if Generate fails.")
    if (torchProbe.stderr) console.warn(torchProbe.stderr)
    if (torchProbe.error) console.warn(String(torchProbe.error))
  }
}

console.log("backend-ok")

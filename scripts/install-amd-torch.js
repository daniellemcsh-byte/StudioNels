/**
 * Install ROCm PyTorch (Windows AMD) into backend/.venv, then Diffusers extras.
 * R9700 / gfx1201 is supported by AMD ROCm 7.2.1 Windows wheels (Python 3.12).
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

function run(args, label) {
  console.log("\n==>", label)
  const r = spawnSync(py, args, {
    cwd: backend,
    stdio: "inherit",
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    windowsHide: true,
  })
  if (r.status !== 0) {
    console.error("FAILED:", label)
    process.exit(r.status || 1)
  }
}

if (!fs.existsSync(py)) {
  console.error("Missing", py)
  console.error("Run Pinokio → Install for StudioNels first.")
  process.exit(1)
}

const ver = spawnSync(py, ["-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], {
  encoding: "utf8",
  windowsHide: true,
})
const pyVer = (ver.stdout || "").trim()
console.log("venv python", py, pyVer)

if (process.platform === "win32") {
  if (pyVer !== "3.12") {
    console.error("")
    console.error("AMD ROCm Windows wheels need Python 3.12 in backend/.venv (found", pyVer || "unknown", ").")
    console.error("Fix: recreate the venv with Python 3.12, then re-run this install.")
    console.error("  1) Install Python 3.12 from python.org (64-bit)")
    console.error("  2) In PowerShell:")
    console.error('     cd C:\\pinokio\\api\\studionels\\backend')
    console.error("     py -3.12 -m venv .venv")
    console.error("     .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    console.error("  3) Pinokio → StudioNels → run Install AMD engine again")
    process.exit(1)
  }

  const base = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1"
  run(["-m", "pip", "install", "--upgrade", "pip"], "upgrade pip")
  run(
    [
      "-m",
      "pip",
      "install",
      "--no-cache-dir",
      `${base}/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl`,
      `${base}/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl`,
      `${base}/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl`,
      `${base}/rocm-7.2.1.tar.gz`,
    ],
    "ROCm SDK 7.2.1",
  )
  run(
    [
      "-m",
      "pip",
      "install",
      "--no-cache-dir",
      `${base}/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl`,
      `${base}/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl`,
      `${base}/torchvision-0.24.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl`,
    ],
    "PyTorch ROCm wheels",
  )
} else {
  console.log("Non-Windows: install ROCm PyTorch from AMD docs first, then continuing with engine extras…")
}

run(["-m", "pip", "install", "-r", "requirements-engine.txt"], "Diffusers + mmgp (native StudioNels speed)")

const check = spawnSync(
  py,
  [
    "-c",
    "import torch; print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available());\n"
      + "print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')",
  ],
  { encoding: "utf8", cwd: backend, windowsHide: true },
)
console.log(check.stdout || "")
if (check.status !== 0) {
  console.error(check.stderr || "")
  console.error("Torch import failed — check AMD Adrenalin driver (26.1.1+ recommended).")
  process.exit(1)
}

if (process.platform === "win32" && !(check.stdout || "").includes("cuda_available True")) {
  console.error("")
  console.error("PyTorch installed but GPU not visible. Install/update:")
  console.error("  AMD Software: Adrenalin Edition 26.1.1 or newer (PyTorch on Windows package).")
  console.error("Then reboot and re-check.")
  process.exit(1)
}

console.log("AMD engine ready.")

/**
 * Shared env for spawning backend/.venv python from Pinokio.
 * Pinokio activates conda base first — that poisons PYTHONPATH/PATH and
 * breaks `import app.main` / ROCm torch DLLs after an AMD engine install.
 */
const path = require("path")
const fs = require("fs")

function venvPython(root) {
  const backend = path.join(root, "backend")
  return process.platform === "win32"
    ? path.join(backend, ".venv", "Scripts", "python.exe")
    : path.join(backend, ".venv", "bin", "python")
}

function cleanEnv(pyPath) {
  const env = { ...process.env, PYTHONUNBUFFERED: "1", PYTHONDONTWRITEBYTECODE: "1" }
  for (const k of [
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "CONDA_PYTHON_EXE",
    "CONDA_PROMPT_MODIFIER",
    "CONDA_SHLVL",
    "VIRTUAL_ENV",
  ]) {
    delete env[k]
  }
  const scripts = path.dirname(pyPath)
  const pathKey = process.platform === "win32" ? "Path" : "PATH"
  const cur = env[pathKey] || env.PATH || env.Path || ""
  const next = [scripts, cur].filter(Boolean).join(path.delimiter)
  env.PATH = next
  env.Path = next
  // Do not force the warm engine on. Opening the app must leave the GPU idle.
  // Settings → Keep model loaded, or Models → Load into studio, turns it on.
  if (!env.STUDIONELS_WARM_ENGINE) env.STUDIONELS_WARM_ENGINE = "0"
  env.MIOPEN_FIND_MODE = env.MIOPEN_FIND_MODE || "FAST"
  env.TORCHINDUCTOR_DISABLE = env.TORCHINDUCTOR_DISABLE || "1"
  env.TORCH_COMPILE_DISABLE = env.TORCH_COMPILE_DISABLE || "1"
  return env
}

function assertVenv(root) {
  const py = venvPython(root)
  if (!fs.existsSync(py)) {
    console.error("Missing", py)
    console.error("Fix: recreate venv with Python 3.12, then reinstall requirements + AMD torch.")
    process.exit(1)
  }
  return py
}

module.exports = { venvPython, cleanEnv, assertVenv }

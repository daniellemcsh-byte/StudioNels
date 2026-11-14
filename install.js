module.exports = {
  run: [
    // venv is relative to `path` — use ".venv" inside backend (NOT "backend/.venv")
    {
      method: "shell.run",
      params: {
        path: "backend",
        venv: ".venv",
        message: [
          "python -m pip install --upgrade pip",
          "python -m pip install -r requirements.txt",
          "python -m pip install -r requirements-engine.txt",
        ],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "frontend",
        message: "npm install",
      },
    },
    {
      method: "notify",
      params: {
        html:
          "StudioNels installed. On AMD: run <b>Install AMD engine</b> next (ROCm PyTorch), then <b>Start</b>.",
      },
    },
  ],
}

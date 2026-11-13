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
        html: "StudioNels installed. Click <b>Start</b>, then Open StudioNels.",
      },
    },
  ],
}

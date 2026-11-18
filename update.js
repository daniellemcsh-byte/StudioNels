module.exports = {
  run: [
    // Kill listeners first — Windows locks run-frontend.js while Start is running,
    // which left users on a stale Vite script (502 / ECONNREFUSED forever).
    {
      method: "shell.run",
      params: {
        message: ["node scripts/free-ports.js"],
      },
    },
    {
      method: "shell.run",
      params: {
        message: ["node scripts/pull-main.js"],
      },
    },
    {
      method: "shell.run",
      params: {
        message: ["node scripts/assert-fresh.js"],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "backend",
        venv: ".venv",
        message: [
          "python -m pip install -r requirements.txt",
          "python -m pip install -r requirements-engine.txt",
          "python -m pip install -U \"diffusers>=0.38.0\"",
          "python -m pip install -U \"safetensors>=0.5.3\"",
        ],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "frontend",
        message: ["npm install"],
      },
    },
    {
      method: "shell.run",
      params: {
        message: ["node scripts/assert-fresh.js"],
      },
    },
    {
      method: "notify",
      params: {
        html:
          "StudioNels updated. Look for <code>update-ok: pull-main 2026-11-18-direct8787</code>. Then <b>Stop → Start</b>. The API now listens on <code>127.0.0.1:8787</code> itself.",
      },
    },
  ],
}

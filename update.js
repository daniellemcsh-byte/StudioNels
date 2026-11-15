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
          "StudioNels updated. You must see <code>update-ok: pull-main 2026-11-15-no502</code> above. Then <b>Start</b>. Vite will wait until the API is ready (no more silent 502).",
      },
    },
  ],
}

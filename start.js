module.exports = {
  daemon: true,
  run: [
    // Kill zombie Vite/uvicorn from a previous Start (cause of 5173→5174 drift)
    {
      method: "shell.run",
      params: {
        message: ["node scripts/free-ports.js"],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "backend",
        venv: ".venv",
        message: [
          "python -m uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8787",
        ],
        on: [
          {
            event: "/Uvicorn running on http:\\/\\/127\\.0\\.0\\.1:8787/i",
            done: true,
          },
        ],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "frontend",
        // strictPort: fail if 5173 busy instead of silently moving to 5174
        message: [
          "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
        ],
        on: [
          {
            // ONLY match the real StudioNels URL — do not match bare "ready in"
            // (that falsely completed when Vite hopped to 5174)
            event: "/Local:\\s+http:\\/\\/127\\.0\\.0\\.1:5173\\//i",
            done: true,
          },
        ],
      },
    },
    {
      method: "local.set",
      params: {
        url: "http://127.0.0.1:5173",
      },
    },
    {
      method: "notify",
      params: {
        html: "StudioNels is running. Open <b>http://127.0.0.1:5173</b> — keep Ollama running in the tray for the Agent LLM.",
      },
    },
  ],
}

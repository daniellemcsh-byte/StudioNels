module.exports = {
  daemon: true,
  run: [
    {
      method: "shell.run",
      params: {
        message: ["node scripts/free-ports.js"],
      },
    },
    {
      method: "shell.run",
      params: {
        message: ["node scripts/check-backend.js"],
      },
    },
    // API must stay up — use venv python directly (not conda base python)
    {
      method: "shell.run",
      params: {
        message: ["node scripts/run-api.js"],
        on: [
          {
            event: "/(Uvicorn running on http:\\/\\/127\\.0\\.0\\.1:8787|Application startup complete)/i",
            done: true,
          },
        ],
      },
    },
    {
      method: "shell.run",
      params: {
        message: ["node scripts/wait-api.js"],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "frontend",
        message: [
          "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
        ],
        on: [
          {
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
        html: "StudioNels is running — click to open inside Pinokio",
        href: "http://127.0.0.1:5173",
      },
    },
  ],
}

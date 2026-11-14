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
    // Spawn API daemon; continue as soon as python is launched.
    // Real readiness is /api/ready via wait-api (avoids Ollama-slow /api/health).
    {
      method: "shell.run",
      params: {
        message: ["node scripts/run-api.js"],
        on: [
          {
            event: "/Using .+python/i",
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
        url: "http://127.0.0.1:5173/",
      },
    },
  ],
}

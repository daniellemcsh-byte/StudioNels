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
    // Start API as a daemon. Do NOT wait on uvicorn log text here —
    // Pinokio can race past that on Windows before the port is bound.
    // Proceed as soon as run-api.js has spawned python, then poll /api/health.
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
    // Sets kernel.memory.local[start.js].url — pinokio.js uses this for in-app Web UI
    {
      method: "local.set",
      params: {
        url: "http://127.0.0.1:5173/",
      },
    },
  ],
}

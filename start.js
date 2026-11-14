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
          // 0.0.0.0 + allowedHosts in vite.config.ts = phone / Tailscale access
          "npm run dev -- --host 0.0.0.0 --port 5173 --strictPort",
        ],
        on: [
          {
            event: "/(Local|Network):\\s+http:\\/\\/(127\\.0\\.0\\.1|0\\.0\\.0\\.0|localhost):5173\\//i",
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

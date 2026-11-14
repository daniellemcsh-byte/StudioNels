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
    // Real readiness is TCP :8787 via wait-api (avoids Ollama-slow /api/health).
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
        message: ["node scripts/run-frontend.js"],
        on: [
          {
            // Match any Vite ready line that mentions port 5173 (Local/Network/IP/Tailscale)
            event: "/:5173\\/?/i",
            done: true,
          },
          {
            // Vite classic banner
            event: "/VITE\\s+v?\\d/i",
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
    {
      method: "notify",
      params: {
        html:
          "StudioNels is running. Open <b>Web UI</b>, or on your phone: <code>http://&lt;your-tailscale-name&gt;:5173</code>",
      },
    },
  ],
}

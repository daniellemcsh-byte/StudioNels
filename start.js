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
    // Spawn API daemon; only mark done once uvicorn has bound :8787.
    // Do NOT match "Using …python" — that prints before torch/ROCm import finishes.
    // wait-api is a TCP fallback if Pinokio missed these log lines.
    {
      method: "shell.run",
      params: {
        message: ["node scripts/run-api.js"],
        on: [
          {
            event: "/Uvicorn running on/i",
            done: true,
          },
          {
            event: "/Application startup complete/i",
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

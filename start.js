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
    // Gateway binds :8787 before importing the heavy app.main stack.
    // Only match “Uvicorn running” (not Application startup) so we never
    // advance wait-api before the socket is actually listening.
    {
      method: "shell.run",
      params: {
        message: ["node scripts/run-api.js"],
        on: [
          {
            event: "/Uvicorn running on/i",
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

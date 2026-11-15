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
    // Keep API shell alive. Prefer “Uvicorn running” (gateway binds fast).
    // Also allow boot-api alive so Pinokio advances to wait-api while python starts.
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
            event: "/boot-api: starting uvicorn/i",
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
    // run-frontend also waits for /api/ready — belt and suspenders against 502.
    {
      method: "shell.run",
      params: {
        message: ["node scripts/run-frontend.js"],
        on: [
          {
            event: "/:5173\\/?/i",
            done: true,
          },
          {
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
          "StudioNels is running. Open <b>Web UI</b>. If create/project still fails, wait for <code>gateway: app.main ready</code> in run-api, then refresh.",
      },
    },
  ],
}

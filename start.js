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
    // Continue as soon as run-api prints its build line / boot-api starts.
    // wait-api (next step) is the real TCP gate; gateway binds :8787 before
    // the heavy app.main import, so this should be seconds — not minutes.
    {
      method: "shell.run",
      params: {
        message: ["node scripts/run-api.js"],
        on: [
          {
            event: "/run-api build /i",
            done: true,
          },
          {
            event: "/boot-api: python alive/i",
            done: true,
          },
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
          "StudioNels is running. Open <b>Web UI</b>. If Generate is empty for a minute, wait for <code>gateway: app.main ready</code> in the run-api terminal.",
      },
    },
  ],
}

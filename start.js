module.exports = {
  daemon: true,
  run: [
    {
      method: "shell.run",
      params: {
        message: ["node scripts/assert-fresh.js"],
      },
    },
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
    {
      method: "shell.run",
      params: {
        message: ["node scripts/run-api.js"],
        on: [
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
          "StudioNels is running. Open <b>Web UI</b>. Stamps must say <code>2026-11-18-direct8787</code>.",
      },
    },
  ],
}

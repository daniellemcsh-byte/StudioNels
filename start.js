module.exports = {
  daemon: true,
  run: [
    {
      method: "shell.run",
      params: {
        path: "backend",
        venv: ".venv",
        message: [
          "python -m uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8787",
        ],
        on: [
          {
            event: "/(Uvicorn running|Application startup complete)/i",
            done: true,
          },
        ],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "frontend",
        message: ["npm run dev -- --host 127.0.0.1 --port 5173"],
        on: [
          {
            event: "/(Local:\\s+http:\\/\\/127\\.0\\.0\\.1:5173|ready in)/i",
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
  ],
}

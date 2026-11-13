module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        message: ["git pull"],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "backend",
        venv: ".venv",
        message: ["python -m pip install -r requirements.txt"],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "frontend",
        message: ["npm install"],
      },
    },
    {
      method: "notify",
      params: {
        html: "StudioNels updated. Click <b>Stop</b> if running, then <b>Start</b>. Open <b>http://127.0.0.1:5173</b> (not 5174).",
      },
    },
  ],
}

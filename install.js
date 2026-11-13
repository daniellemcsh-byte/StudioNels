module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        message: "python -m venv backend/.venv",
      },
    },
    {
      method: "shell.run",
      params: {
        venv: "backend/.venv",
        path: "backend",
        message: [
          "python -m pip install --upgrade pip",
          "pip install -r requirements.txt",
        ],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "frontend",
        message: "npm install",
      },
    },
    {
      method: "notify",
      params: {
        html: "StudioNels installed. Click <b>Start</b>, then Open StudioNels.",
      },
    },
  ],
}

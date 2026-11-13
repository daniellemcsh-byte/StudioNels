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
        venv: "backend/.venv",
        path: "backend",
        message: ["pip install -r requirements.txt"],
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
        html: "StudioNels updated.",
      },
    },
  ],
}

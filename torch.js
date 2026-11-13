module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        venv: "backend/.venv",
        path: "backend",
        message: [
          "pip install -r requirements-engine.txt",
        ],
      },
    },
    {
      method: "notify",
      params: {
        html: "Engine extras installed. On Windows+AMD, real ROCm gens may still be limited — preview + Director upload still work.",
      },
    },
  ],
}

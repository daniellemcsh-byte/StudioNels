module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        path: "backend",
        venv: ".venv",
        message: [
          "python -m pip install -r requirements-engine.txt",
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

module.exports = {
  run: [
    // venv is relative to `path` — use ".venv" inside backend (NOT "backend/.venv")
    {
      method: "shell.run",
      params: {
        path: "backend",
        venv: ".venv",
        message: [
          "python -m pip install --upgrade pip",
          "python -m pip install -r requirements.txt",
          "python -m pip install -r requirements-engine.txt",
          "python -m pip install --no-deps -r requirements-nodeps.txt",
        ],
      },
    },
    // ACE-Step 1.5 code (MIT) for songs/score. Pinned commit; weights download from the Models tab.
    {
      when: "{{!exists('vendor/ACE-Step-1.5')}}",
      method: "shell.run",
      params: {
        message: [
          "git clone https://github.com/ace-step/ACE-Step-1.5.git vendor/ACE-Step-1.5",
          "git -C vendor/ACE-Step-1.5 checkout ca1e85fe9430179831e6bc6be790c332190a3866",
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
        html:
          "StudioNels installed. On AMD: run <b>Install AMD engine</b> next (ROCm PyTorch), then <b>Start</b>.",
      },
    },
  ],
}

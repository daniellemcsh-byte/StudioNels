module.exports = {
  run: [
    // Kill listeners first — Windows locks run-frontend.js while Start is running,
    // which left users on a stale Vite script (502 / ECONNREFUSED forever).
    {
      method: "shell.run",
      params: {
        message: ["node scripts/free-ports.js"],
      },
    },
    {
      method: "shell.run",
      params: {
        message: ["node scripts/pull-main.js"],
      },
    },
    {
      method: "shell.run",
      params: {
        message: ["node scripts/assert-fresh.js"],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "backend",
        venv: ".venv",
        message: [
          "python -m pip install -r requirements.txt",
          "python -m pip install -r requirements-engine.txt",
          "python -m pip install --no-deps -r requirements-nodeps.txt",
          "python -m pip install -U \"diffusers>=0.38.0\"",
          "python -m pip install -U \"safetensors>=0.5.3\"",
        ],
      },
    },
    // ACE-Step 1.5 code for songs/score (same pinned commit as install.js)
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
        message: ["npm install"],
      },
    },
    {
      method: "shell.run",
      params: {
        message: ["node scripts/assert-fresh.js"],
      },
    },
    {
      method: "notify",
      params: {
        html:
          "StudioNels updated. Look for <code>update-ok: pull-main 2026-11-18-idlegpu</code>. Then <b>Stop → Start</b>. The GPU stays idle until you press Generate.",
      },
    },
  ],
}

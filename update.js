module.exports = {
  run: [
    // Force latest main — Pinokio Update used to leave stale wait-api.js behind.
    {
      method: "shell.run",
      params: {
        message: [
          "git fetch origin",
          "git checkout main",
          "git reset --hard origin/main",
          "git clean -fd scripts",
        ],
      },
    },
    {
      method: "shell.run",
      params: {
        path: "backend",
        venv: ".venv",
        message: [
          "python -m pip install -r requirements.txt",
          // Diffusers + mmgp — without this, Generate sits at 3% and says install requirements-engine.txt
          "python -m pip install -r requirements-engine.txt",
          // LTX-2 / LTX-2.5 Distilled need LTX2Pipeline (Diffusers 0.38+)
          "python -m pip install -U \"diffusers>=0.38.0\"",
          // Force safetensors new enough for transformers' safe_open(..., backend=...)
          "python -m pip install -U \"safetensors>=0.5.3\"",
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
        message: [
          "node -e \"const w=require('fs').readFileSync('scripts/wait-api.js','utf8'); if(!w.includes('2026-11-15-no502')){console.error('UPDATE DID NOT LAND no502 wait-api'); process.exit(1)}; console.log('update-ok: wait-api build 2026-11-15-no502')\"",
        ],
      },
    },
    {
      method: "notify",
      params: {
        html:
          "StudioNels updated (fixes Vite 502 / API-down). Next: <b>Stop</b> → <b>Start</b>. wait-api must say <code>2026-11-15-no502</code>. Vite will not start until the API is ready.",
      },
    },
  ],
}

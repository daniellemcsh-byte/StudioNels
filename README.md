# Framewright

A fully local AI film studio for AMD Radeon GPUs. Describe an idea, keep character and scene profiles, let a local agent break the story into editable shots, generate on-device, then refine in Sampling and Director mode.

Designed to stay usable on modest VRAM (8–12 GB+) while taking advantage of cards like the Radeon AI PRO R9700 32 GB when available.

## What you get

- **Agent** — tell your idea in plain language; get a shot list you can edit
- **Profiles** — character + scene cards the planner reuses
- **Shots** — every beat is editable before / after generation
- **Storyboard** — visual planning board
- **Characters** — generate or import look references for people and places
- **Sampling** — pick takes after generation
- **Director** — pin clips on a timeline and edit as you go
- **Save** — projects persist on disk so you can power off and continue

Nothing leaves your machine. No cloud accounts required.

## Quick start

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8787
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### 3. Optional local AI services

| Service | Role | Suggested install |
|--------|------|-------------------|
| [Ollama](https://ollama.com) | Planning agent | `ollama pull llama3.2:3b` (low RAM) or `llama3.1:8b` |
| [ComfyUI](https://github.com/comfyanonymous/ComfyUI) + ROCm | Image / video gen on AMD | See `docs/AMD_ROCM.md` |

Without Ollama / ComfyUI the app still runs: the agent uses a built-in planner, and generation creates local preview placeholders so you can learn the studio flow.

## Hardware profiles

Pick a preset in **Settings → Compute**, or copy from `presets/`:

| Preset | VRAM target | Notes |
|--------|-------------|--------|
| `amd-r9700.json` | ~20–28 GB | Your 32 GB R9700 Pro — higher quality, longer clips |
| `amd-low-vram.json` | ~6–10 GB | Default for sharing with others |
| `cpu-fallback.json` | 0 GB GPU | Planning + UI only; slow image drafts |

Framewright defaults to the **low-VRAM** path so more people can use it. On the R9700 you can switch to the high preset anytime.

## Project data

Saved under `~/.framewright/projects/` (JSON + media). Hit **Save** or rely on autosave.

## Docs

- `docs/AMD_ROCM.md` — ROCm, PyTorch, ComfyUI on Radeon
- `docs/MODELS.md` — recommended local models by VRAM
- `docs/WORKFLOW.md` — Agent → Profiles → Shots → Generate → Sampling → Director

## License

MIT — run it, fork it, ship it for your crew.

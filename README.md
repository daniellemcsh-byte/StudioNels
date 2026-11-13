# StudioNels

Fully local AI film studio for AMD Radeon GPUs — Wan2GP-style, no ComfyUI.

Describe an idea, keep character/scene profiles, plan editable shots, then generate with a **built-in engine** (no ComfyUI):

| Mode | Meaning |
|------|---------|
| **t2i** | Text → Image |
| **t2v** | Text → Video |
| **i2v** | Image → Video |
| **ref2i** | Reference → Image |
| **ref2v** | Reference → Video |

Plus Agent, Profiles, Shots, Storyboard, Sampling, Director, and Save-to-disk.

## Quick start

```bash
# API
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8787

# UI
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 → **Generate** tab.

### Real GPU generation (AMD)

1. Install **ROCm PyTorch** for your Radeon  
2. `pip install -r backend/requirements-engine.txt`  
3. Pick a model in Generate (Wan 1.3B / SDXL Turbo / …)

Until then the built-in **preview engine** still runs every mode so you can learn the studio.

See `docs/AMD_ROCM.md` and `docs/MODELS.md`.

## Presets

| Preset | Target |
|--------|--------|
| `amd-low-vram` | ~8GB — default, shareable |
| `amd-r9700` | your 32GB R9700 Pro |
| `cpu-fallback` | preview / UI only |

## Data

`~/.studionels/projects/`, `media/`, `models/`, `jobs.json`

## License

MIT

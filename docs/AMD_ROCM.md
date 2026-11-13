# AMD ROCm — built-in engine (no ComfyUI)

Nellwright loads Diffusers / Wan pipelines **inside the app**, Wan2GP-style.

## 1. Install ROCm PyTorch

Follow AMD’s ROCm + PyTorch guide for your OS. Then verify:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

On ROCm, `torch.cuda` is the AMD device API.

## 2. Install engine extras

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-engine.txt
```

## 3. Download a model

First run will pull from Hugging Face into `~/.nellwright/models` (or the Hugging Face cache). Start with:

- **T2V:** `Wan-AI/Wan2.1-T2V-1.3B-Diffusers` (low VRAM)
- **T2I:** `stabilityai/sdxl-turbo`
- **I2V / Ref2V:** LTX-Video or Wan I2V when you have more VRAM

Use the **Generate** tab → pick mode → Generate.

## 4. Low VRAM habits

- Keep **CPU offload** on (Settings / preset)
- Prefer 1.3B Wan / SDXL Turbo / short frame counts
- One job at a time (default)
- Draft at 480p, then promote winners in Sampling

## R9700 32GB

Switch preset to **amd-r9700** for longer clips and heavier I2V models. Still sequential jobs so the desktop stays usable.

# AMD ROCm setup (Radeon)

Framewright talks to local services. On AMD, video/image generation usually goes through **ComfyUI + ROCm PyTorch**.

## R9700 / RDNA-class cards

1. Install the latest AMD ROCm stack for your OS (Ubuntu recommended for ROCm).
2. Install PyTorch with ROCm wheels from AMD / PyTorch docs for your ROCm version.
3. Verify:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

On ROCm, `torch.cuda` is the AMD device API (name is historical).

4. Clone ComfyUI, install requirements against that PyTorch, launch:

```bash
python main.py --listen 127.0.0.1 --port 8188
```

5. In Framewright → Settings, set ComfyUI URL to `http://127.0.0.1:8188`.

## Low VRAM habits (shareable builds)

- Prefer **LTX-Video** or small **Wan** variants for drafts
- 480p / short clips (2–4 s) first; upscale later if needed
- Enable CPU offload / sequential decode in the low-VRAM preset
- Keep only one generation job active
- Use 3B–8B chat models for the agent (`llama3.2:3b` is fine)

## Agent (Ollama)

```bash
ollama pull llama3.2:3b
ollama serve
```

Framewright defaults to `http://127.0.0.1:11434` and model `llama3.2:3b`.

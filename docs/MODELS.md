# Local models by VRAM

## Planning agent (Ollama)

| VRAM / RAM | Model | Why |
|------------|-------|-----|
| Shared / low | `llama3.2:3b` | Fast, small, good enough for shot lists |
| 16 GB+ system RAM | `llama3.1:8b` | Stronger structure & dialogue |
| Plenty of headroom | `qwen2.5:14b` | Better directing notes |

## Image / character stills

| VRAM | Model family |
|------|----------------|
| 6–10 GB | SDXL Turbo / Lightning, or Flux-schnell GGUF / NF4 if supported |
| 16 GB+ | SDXL full, Flux-dev quantized |
| 24–32 GB | Higher-res Flux / SD3-class |

## Video

| VRAM | Start here |
|------|------------|
| 8–12 GB | LTX-Video short clips, 480p |
| 16–24 GB | Wan 1.3B / LTX longer |
| 32 GB (R9700) | Wan larger / longer clips, better consistency |

Always draft short. Promote winners in **Sampling**, then assemble in **Director**.

Hugging Face / GitHub weights are for **your** local runtimes (ComfyUI, Diffusers). Framewright orchestrates them; it does not redistribute model weights.

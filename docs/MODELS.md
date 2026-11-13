# Built-in models (in-app)

Framewright does **not** use ComfyUI graphs. Models load via Diffusers inside the process.

## By mode

| Mode | Low VRAM start | More VRAM |
|------|----------------|-----------|
| t2i | SDXL Turbo | FLUX Schnell |
| t2v | Wan 2.1 T2V 1.3B | longer frames / larger Wan |
| i2v | LTX-Video | Wan 2.1 I2V 14B |
| ref2i | SDXL Turbo (+ ref image) | FLUX when supported |
| ref2v | LTX / Wan I2V with reference | Wan I2V 14B |

## Agent (planning only)

| RAM | Ollama model |
|-----|----------------|
| Low | `llama3.2:3b` |
| Comfortable | `llama3.1:8b` |

Weights come from Hugging Face into the local cache / `~/.framewright/models`. You run them; Framewright does not redistribute checkpoints.

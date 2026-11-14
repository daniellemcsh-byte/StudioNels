# AMD ROCm — real generation (no ComfyUI)

StudioNels loads Diffusers / Wan pipelines **inside the app**. Your **Radeon AI PRO R9700** is supported on **Windows 11** with AMD’s ROCm 7.2.1 PyTorch wheels.

## Fast path (Pinokio)

1. Install/update **AMD Adrenalin 26.1.1+** (PyTorch on Windows / ROCm-capable driver).
2. StudioNels venv must be **Python 3.12** (ROCm Windows wheels are cp312 only).
3. In Pinokio → StudioNels → run **Install AMD engine** (runs `torch.js`).
4. **Stop** → **Start** StudioNels.
5. Settings → preset **AMD Radeon AI PRO R9700 32GB** → Save.
6. Generate / Film night again — home pill should show your GPU, not “preview”.

## Manual install (PowerShell)

```powershell
cd C:\pinokio\api\studionels\backend

# If .venv is not 3.12:
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# ROCm SDK + PyTorch (AMD repo)
.\.venv\Scripts\python.exe -m pip install --no-cache-dir `
  https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl `
  https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl `
  https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl `
  https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm-7.2.1.tar.gz

.\.venv\Scripts\python.exe -m pip install --no-cache-dir `
  https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl `
  https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl `
  https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torchvision-0.24.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl

.\.venv\Scripts\python.exe -m pip install -r requirements-engine.txt

.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
.\.venv\Scripts\python.exe -c "import mmgp; print('mmgp ok')"
```

Expect: `True` and something like `AMD Radeon AI PRO R9700`, plus `mmgp ok`.

Official guide: https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installrad/windows/install-pytorch.html

## After install

- StudioNels Generate uses **mmgp natively** (same library as Wan2GP) — you do **not** need to link Wan2GP for speed.
- First Generate may download model weights (Wan 1.3B / SDXL Turbo, etc.) into the HF cache — that can take a while.
- Keep **one job at a time** (default).
- On R9700 use preset **Max VRAM / amd-r9700**.

## Still preview?

- Driver too old → Adrenalin 26.1.1+
- Wrong Python → must be 3.12 in `.venv`
- StudioNels not restarted after pip install → Stop/Start
- Torch CPU-only wheel still installed → re-run the AMD wheel commands above

// Install Diffusers extras + (on Windows) AMD ROCm PyTorch wheels for Radeon.
module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        message: ["node scripts/install-amd-torch.js"],
      },
    },
    {
      method: "notify",
      params: {
        html: "AMD engine install finished. Stop → Start StudioNels, set preset <b>amd-r9700</b>, then Generate again.",
      },
    },
  ],
}

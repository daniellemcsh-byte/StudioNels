const path = require("path")

module.exports = {
  version: "1.9",
  title: "StudioNels",
  description:
    "Local AI film studio for AMD — Agent, Film night, Director, upload clips. Wan2GP-style built-in engine (no ComfyUI).",
  icon: "icon.png",
  menu: async (kernel, info) => {
    const installing = info.running("install.js")
    const updating = info.running("update.js")
    const installingTorch = info.running("torch.js")
    const running = info.running("start.js")
    const installed = info.exists("backend/.venv") || info.exists("frontend/node_modules")

    if (installing) {
      return [
        {
          default: true,
          icon: "fa-solid fa-plug",
          text: "Installing",
          href: "install.js",
        },
      ]
    }

    if (installingTorch) {
      return [
        {
          default: true,
          icon: "fa-solid fa-microchip",
          text: "Installing AMD engine…",
          href: "torch.js",
        },
      ]
    }

    if (updating) {
      return [
        {
          default: true,
          icon: "fa-solid fa-rotate",
          text: "Updating",
          href: "update.js",
        },
      ]
    }

    if (running) {
      const local = kernel.memory.local[path.resolve(__dirname, "start.js")]
      if (local && local.url) {
        return [
          {
            default: true,
            icon: "fa-solid fa-house",
            text: "Web UI",
            href: local.url,
          },
          {
            icon: "fa-solid fa-terminal",
            text: "Terminal",
            href: "start.js",
          },
          {
            icon: "fa-solid fa-power-off",
            text: "Stop",
            href: "start.js",
            params: { kill: true },
          },
          {
            icon: "fa-solid fa-microchip",
            text: "Install AMD engine (stop first)",
            href: "torch.js",
          },
        ]
      }
      return [
        {
          default: true,
          icon: "fa-solid fa-terminal",
          text: "Starting…",
          href: "start.js",
        },
      ]
    }

    if (installed) {
      return [
        {
          default: true,
          icon: "fa-solid fa-power-off",
          text: "Start",
          href: "start.js",
        },
        {
          icon: "fa-solid fa-microchip",
          text: "Install AMD engine",
          href: "torch.js",
        },
        {
          icon: "fa-solid fa-rotate",
          text: "Update",
          href: "update.js",
        },
        {
          icon: "fa-solid fa-plug",
          text: "Install",
          href: "install.js",
        },
        {
          icon: "fa-solid fa-book",
          text: "Docs (AMD ROCm)",
          href: "docs/AMD_ROCM.md",
        },
      ]
    }

    return [
      {
        default: true,
        icon: "fa-solid fa-plug",
        text: "Install",
        href: "install.js",
      },
    ]
  },
}

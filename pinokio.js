const path = require("path")

module.exports = {
  version: "1.8",
  title: "StudioNels",
  description:
    "Local AI film studio for AMD — Agent, Film night, Director, upload clips. Wan2GP-style built-in engine (no ComfyUI).",
  icon: "icon.png",
  menu: async (kernel, info) => {
    const installing = info.running("install.js")
    const updating = info.running("update.js")
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
        // default:true + http href (no popout) → Pinokio shows the UI inside the app page
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
        ]
      }
      // Still booting — keep Terminal until local.url is set
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
          text: "Docs",
          href: "docs/FOLDERS.md",
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

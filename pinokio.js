const path = require("path")

module.exports = {
  version: "1.7",
  title: "StudioNels",
  description:
    "Local AI film studio for AMD — Agent, Film night, Director, upload clips. Wan2GP-style built-in engine (no ComfyUI).",
  icon: "icon.png",
  menu: async (kernel, info) => {
    const installed = info.exists("backend/.venv") || info.exists("frontend/node_modules")
    const running = info.running("start.js")
    // Pinokio stores start.js locals under the absolute script path
    const mem =
      (running && kernel.memory?.local?.[path.resolve(__dirname, "start.js")]) ||
      (running && info.local?.("start.js")) ||
      null
    const openUrl = (mem && mem.url) || "http://127.0.0.1:5173"
    let menu = []

    if (running) {
      menu.push({
        icon: "fa-solid fa-terminal",
        text: "Terminal",
        href: "start.js",
      })
      // No target/_blank and no popout → opens inside Pinokio
      menu.push({
        icon: "fa-solid fa-house",
        text: "Open StudioNels",
        href: openUrl,
        default: true,
      })
      menu.push({
        icon: "fa-solid fa-arrow-up-right-from-square",
        text: "Open in browser",
        href: openUrl,
        popout: true,
      })
      menu.push({
        icon: "fa-solid fa-power-off",
        text: "Stop",
        href: "start.js",
        params: { kill: true },
      })
    } else if (installed) {
      menu.push({
        icon: "fa-solid fa-power-off",
        text: "Start",
        href: "start.js",
        default: true,
      })
      menu.push({
        icon: "fa-solid fa-rotate",
        text: "Update",
        href: "update.js",
      })
      menu.push({
        icon: "fa-solid fa-plug",
        text: "Install",
        href: "install.js",
      })
    } else {
      menu.push({
        icon: "fa-solid fa-plug",
        text: "Install",
        href: "install.js",
        default: true,
      })
    }

    menu.push({
      icon: "fa-solid fa-book",
      text: "Docs (folders)",
      href: "docs/FOLDERS.md",
    })
    return menu
  },
}

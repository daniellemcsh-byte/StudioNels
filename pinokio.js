const path = require("path")

module.exports = {
  version: "1.5",
  title: "StudioNels",
  description:
    "Local AI film studio for AMD — Agent, Film night, Director, upload clips. Wan2GP-style built-in engine (no ComfyUI).",
  icon: "icon.png",
  menu: async (kernel, info) => {
    const installed = info.exists("backend/.venv") || info.exists("frontend/node_modules")
    const running = info.running("start.js")
    let menu = []

    if (running) {
      menu.push({
        icon: "fa-solid fa-terminal",
        text: "Terminal",
        href: "start.js",
      })
      menu.push({
        icon: "fa-solid fa-house",
        text: "Open StudioNels",
        href: "http://127.0.0.1:5173",
        target: "_blank",
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
      })
    }

    menu.push({
      icon: "fa-solid fa-book",
      text: "Docs (folders)",
      href: "docs/FOLDERS.md",
      target: "_blank",
    })
    return menu
  },
}

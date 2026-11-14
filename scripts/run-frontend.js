/**
 * Launch Vite for Pinokio — host 0.0.0.0 + Tailscale MagicDNS allowed.
 * Avoids relying on Pinokio shell.run `env` (not all builds pass it through).
 */
const { spawn } = require("child_process")
const path = require("path")

const frontend = path.join(__dirname, "..", "frontend")
const env = {
  ...process.env,
  __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS: ".ts.net",
}

const npm = process.platform === "win32" ? "npm.cmd" : "npm"
console.log("Starting Vite on 0.0.0.0:5173 (Tailscale / LAN OK)")

const child = spawn(
  npm,
  ["run", "dev", "--", "--host", "0.0.0.0", "--port", "5173", "--strictPort"],
  {
    cwd: frontend,
    env,
    stdio: "inherit",
    windowsHide: true,
    shell: process.platform === "win32",
  },
)

child.on("exit", (code, signal) => {
  console.error("Vite exited", { code, signal })
  process.exit(code || 1)
})

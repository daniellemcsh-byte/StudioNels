/**
 * Free StudioNels ports before Start (Windows + Unix).
 * Stops zombie Vite/uvicorn that make Pinokio open the wrong URL.
 */
const { execSync } = require("child_process")

const PORTS = [5173, 5174, 8787]

function freeWindows(port) {
  try {
    const out = execSync(`netstat -ano | findstr :${port}`, {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      windowsHide: true,
    })
    const pids = new Set()
    for (const line of out.split(/\r?\n/)) {
      if (!/LISTENING/i.test(line)) continue
      const parts = line.trim().split(/\s+/)
      const pid = parts[parts.length - 1]
      if (pid && /^\d+$/.test(pid) && pid !== "0") pids.add(pid)
    }
    for (const pid of pids) {
      try {
        execSync(`taskkill /F /PID ${pid}`, {
          stdio: "ignore",
          windowsHide: true,
        })
        console.log(`Freed port ${port} (PID ${pid})`)
      } catch {
        /* already gone */
      }
    }
  } catch {
    /* nothing listening */
  }
}

function freeUnix(port) {
  try {
    const out = execSync(`lsof -ti tcp:${port} -sTCP:LISTEN || true`, {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      shell: "/bin/bash",
    })
    for (const pid of out.split(/\s+/).filter(Boolean)) {
      try {
        execSync(`kill -9 ${pid}`, { stdio: "ignore" })
        console.log(`Freed port ${port} (PID ${pid})`)
      } catch {
        /* already gone */
      }
    }
  } catch {
    /* nothing listening */
  }
}

const free = process.platform === "win32" ? freeWindows : freeUnix
for (const port of PORTS) free(port)
console.log("Ports ready:", PORTS.join(", "))

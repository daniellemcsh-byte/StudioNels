/**
 * Free StudioNels ports before Start (Windows + Unix).
 * Stops zombie Vite/uvicorn that make Pinokio open the wrong URL.
 */
const { execSync } = require("child_process")

const PORTS = [5173, 5174, 8787, 8788]

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
// On Windows, lingering sockets can flap "address already in use" if we bind
// immediately after taskkill. Brief pause so :8787 is really free.
if (process.platform === "win32") {
  try {
    execSync("timeout /t 1 /nobreak >nul", {
      stdio: "ignore",
      windowsHide: true,
      shell: true,
    })
  } catch {
    // timeout.exe missing or interrupted — Atomics wait fallback (~1s)
    try {
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 1000)
    } catch {
      /* ignore */
    }
  }
}
console.log("Ports ready:", PORTS.join(", "))

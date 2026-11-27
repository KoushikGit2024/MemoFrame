"use strict";

const fs = require("fs");
const path = require("path");
const { spawn, execFile } = require("child_process");
const readline = require("readline");
const { app } = require("electron");

class BackendClient {
  constructor(appRoot, onEvent) {
    this.appRoot = appRoot;
    this.repoRoot = this._resolveRepoRoot(appRoot);
    this.onEvent = onEvent || (() => {});
    this.proc = null;
    this.nextId = 1;
    this.pending = new Map();
    this.closed = false;
  }

  _resolveRepoRoot(appRoot) {
    const grandParent = path.resolve(appRoot, "..", "..");
    if (fs.existsSync(path.join(grandParent, "services", "engine", "memoframe_engine", "rpc", "server.py"))) {
      return grandParent;
    }
    const parent = path.resolve(appRoot, "..");
    if (fs.existsSync(path.join(parent, "services", "engine", "memoframe_engine", "rpc", "server.py"))) {
      return parent;
    }
    return grandParent;
  }

  _resolveWritableWorkspace() {
    if (process.env.MEMOFRAME_WORKSPACE) {
      return path.resolve(process.env.MEMOFRAME_WORKSPACE);
    }
    if (app && app.isPackaged) {
      const ws = path.join(app.getPath("userData"), "workspace");
      fs.mkdirSync(ws, { recursive: true });
      return ws;
    }
    return "";
  }

  _pythonCandidates() {
    const list = [];
    if (process.env.MEMOFRAME_PYTHON) list.push(process.env.MEMOFRAME_PYTHON);
    const isWin = process.platform === "win32";
    const rels = isWin
      ? [
          [".venv", "Scripts", "python.exe"],
          ["venv", "Scripts", "python.exe"],
          ["services", "engine", ".venv", "Scripts", "python.exe"],
          ["services", "engine", "venv", "Scripts", "python.exe"],
        ]
      : [
          [".venv", "bin", "python"],
          ["venv", "bin", "python"],
          ["services", "engine", ".venv", "bin", "python"],
          ["services", "engine", "venv", "bin", "python"],
        ];
    for (const parts of rels) {
      const candidate = path.join(this.repoRoot, ...parts);
      if (fs.existsSync(candidate)) list.push(candidate);
    }
    list.push(...(isWin ? ["python", "python3"] : ["python3", "python"]));
    return list;
  }

  start() {
    if (this.proc) return;
    this.closed = false;
    if (app && app.isPackaged && process.resourcesPath) {
      const exeName = process.platform === "win32" ? "server.exe" : "server";
      const packagedExe = path.join(process.resourcesPath, "bridge-bin", exeName);
      if (fs.existsSync(packagedExe)) {
        this._spawnWithFallback([packagedExe], 0);
        return;
      }
    }
    this._spawnWithFallback(this._pythonCandidates(), 0);
  }

  _spawnWithFallback(candidates, index) {
    const exe = candidates[index];
    const isPackaged = Boolean(app && app.isPackaged);
    const writableWorkspace = this._resolveWritableWorkspace();
    const engineRoot = process.env.MEMOFRAME_ENGINE_DIR || path.join(this.repoRoot, "services", "engine");
    const bundledModelsDir =
      isPackaged && process.resourcesPath
        ? path.join(process.resourcesPath, "models")
        : "";

    const env = {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      MEMOFRAME_ENGINE_DIR: engineRoot,
      ...(writableWorkspace ? { MEMOFRAME_WORKSPACE: writableWorkspace } : {}),
      ...(bundledModelsDir && fs.existsSync(bundledModelsDir)
        ? { MEMOFRAME_BUNDLED_MODELS_DIR: bundledModelsDir }
        : {}),
      PYTHONPATH: [engineRoot, this.repoRoot, process.env.PYTHONPATH || ""]
        .filter(Boolean)
        .join(path.delimiter),
    };

    const isFrozenExe = exe.endsWith("server.exe") || path.basename(exe) === "server";
    const spawnCwd = isPackaged && writableWorkspace ? writableWorkspace : this.repoRoot;
    const child = spawn(exe, isFrozenExe ? [] : ["-m", "memoframe_engine.rpc.server"], {
      cwd: spawnCwd,
      env,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });

    this.proc = child;

    child.on("error", err => {
      if (index + 1 < candidates.length) {
        this._spawnWithFallback(candidates, index + 1);
        return;
      }
      this._rejectAll(new Error(`Failed to launch Python bridge (${exe}): ${err.message}`));
    });

    child.stderr.on("data", chunk => {
      const msg = chunk.toString("utf8").trim();
      if (msg) this.onEvent("bridge.stderr", { message: msg });
    });

    const rl = readline.createInterface({ input: child.stdout, crlfDelay: Infinity });
    rl.on("line", line => this._handleLine(line));

    child.on("exit", (code, signal) => {
      if (this.proc === child) this.proc = null;
      if (!this.closed) {
        this._rejectAll(
          new Error(`Python bridge exited unexpectedly (code=${code}, signal=${signal})`)
        );
        this.onEvent("bridge.exited", { code, signal });
      }
    });
  }

  _handleLine(raw) {
    const trimmed = raw.trim();
    if (!trimmed) return;
    let msg;
    try {
      msg = JSON.parse(trimmed);
    } catch {
      return;
    }

    if (msg.event) {
      this.onEvent(msg.event, msg.data);
      return;
    }

    const entry = this.pending.get(msg.id);
    if (!entry) return;
    this.pending.delete(msg.id);
    clearTimeout(entry.timer);

    if (msg.ok) {
      entry.resolve(msg.result);
    } else {
      const errObj = msg.error || {};
      const err = new Error(errObj.message || "Backend RPC error");
      err.code = errObj.code || "RPC_ERROR";
      err.hint = errObj.hint || "";
      entry.reject(err);
    }
  }

  _rejectAll(err) {
    for (const [id, entry] of this.pending.entries()) {
      clearTimeout(entry.timer);
      entry.reject(err);
      this.pending.delete(id);
    }
  }

  call(method, params = {}, timeoutMs = 120000) {
    return new Promise((resolve, reject) => {
      if (!this.proc || !this.proc.stdin.writable) {
        reject(new Error("Python bridge process is not running."));
        return;
      }
      const id = this.nextId++;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`RPC timeout calling ${method}`));
      }, timeoutMs);

      this.pending.set(id, { resolve, reject, timer });
      const payload = JSON.stringify({ id, method, params }) + "\n";
      this.proc.stdin.write(payload, "utf8");
    });
  }

  stop() {
    this.closed = true;
    this._rejectAll(new Error("Application shutting down."));
    const ref = this.proc;
    this.proc = null;
    if (!ref) return Promise.resolve();

    return new Promise(resolve => {
      let settled = false;
      const done = () => {
        if (settled) return;
        settled = true;
        clearTimeout(killTimer);
        resolve();
      };

      ref.once("exit", done);

      try {
        if (ref.stdin && !ref.stdin.destroyed) ref.stdin.end();
      } catch {
        // ignore
      }

      const killTimer = setTimeout(() => {
        if (ref.exitCode !== null || ref.killed) {
          done();
          return;
        }
        if (process.platform === "win32" && ref.pid) {
          execFile(
            "taskkill",
            ["/pid", String(ref.pid), "/T", "/F"],
            { windowsHide: true },
            () => done()
          );
        } else {
          try {
            ref.kill("SIGKILL");
          } catch {
            // ignore
          }
          done();
        }
      }, 1500);
    });
  }
}

module.exports = { BackendClient };

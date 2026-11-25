'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const readline = require('readline');

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
    const parent = path.resolve(appRoot, '..');
    if (fs.existsSync(path.join(parent, 'bridge', 'server.py'))) {
      return parent;
    }
    if (fs.existsSync(path.join(appRoot, 'bridge', 'server.py'))) {
      return appRoot;
    }
    if (process.resourcesPath && fs.existsSync(path.join(process.resourcesPath, 'bridge', 'server.py'))) {
      return process.resourcesPath;
    }
    return parent;
  }

  _pythonCandidates() {
    const list = [];
    if (process.env.MEMOFRAME_PYTHON) list.push(process.env.MEMOFRAME_PYTHON);
    const isWin = process.platform === 'win32';
    const rels = isWin
      ? [
          ['.venv', 'Scripts', 'python.exe'],
          ['venv', 'Scripts', 'python.exe'],
          ['backend', '.venv', 'Scripts', 'python.exe'],
          ['backend', 'venv', 'Scripts', 'python.exe'],
        ]
      : [
          ['.venv', 'bin', 'python'],
          ['venv', 'bin', 'python'],
          ['backend', '.venv', 'bin', 'python'],
          ['backend', 'venv', 'bin', 'python'],
        ];
    for (const parts of rels) {
      const candidate = path.join(this.repoRoot, ...parts);
      if (fs.existsSync(candidate)) list.push(candidate);
    }
    list.push(...(isWin ? ['python', 'python3'] : ['python3', 'python']));
    return list;
  }

  start() {
    if (this.proc) return;
    this._spawnWithFallback(this._pythonCandidates(), 0);
  }

  _spawnWithFallback(candidates, index) {
    const exe = candidates[index];
    const backendDir = process.env.MEMOFRAME_BACKEND_DIR || path.join(this.repoRoot, 'backend');
    const env = {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      MEMOFRAME_BACKEND_DIR: backendDir,
      PYTHONPATH: [this.repoRoot, backendDir, process.env.PYTHONPATH || '']
        .filter(Boolean)
        .join(path.delimiter),
    };

    const child = spawn(exe, ['-m', 'bridge.server'], {
      cwd: this.repoRoot,
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });

    this.proc = child;

    child.on('error', (err) => {
      if (index + 1 < candidates.length) {
        this._spawnWithFallback(candidates, index + 1);
        return;
      }
      this._rejectAll(new Error(`Failed to launch Python bridge (${exe}): ${err.message}`));
    });

    child.stderr.on('data', (chunk) => {
      const msg = chunk.toString('utf8').trim();
      if (msg) this.onEvent('bridge.stderr', { message: msg });
    });

    const rl = readline.createInterface({ input: child.stdout, crlfDelay: Infinity });
    rl.on('line', (line) => this._handleLine(line));

    child.on('exit', (code, signal) => {
      this.proc = null;
      if (!this.closed) {
        this._rejectAll(new Error(`Python bridge exited unexpectedly (code=${code}, signal=${signal})`));
        this.onEvent('bridge.exited', { code, signal });
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
      const err = new Error(errObj.message || 'Backend RPC error');
      err.code = errObj.code || 'RPC_ERROR';
      err.hint = errObj.hint || '';
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
        reject(new Error('Python bridge process is not running.'));
        return;
      }
      const id = this.nextId++;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`RPC timeout calling ${method}`));
      }, timeoutMs);

      this.pending.set(id, { resolve, reject, timer });
      const payload = JSON.stringify({ id, method, params }) + '\n';
      this.proc.stdin.write(payload, 'utf8');
    });
  }

  stop() {
    this.closed = true;
    this._rejectAll(new Error('Application shutting down.'));
    if (!this.proc) return;
    try {
      this.proc.stdin.end();
    } catch {
      // ignore
    }
    const ref = this.proc;
    setTimeout(() => {
      try {
        if (!ref.killed) ref.kill();
      } catch {
        // ignore
      }
    }, 1500);
    this.proc = null;
  }
}

module.exports = { BackendClient };

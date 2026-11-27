"use strict";

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const { app, BrowserWindow, net, protocol } = require("electron");

const { BackendClient } = require("./backend-client");
const { registerIpcHandlers } = require("./ipc-handlers");

const APP_ROOT = path.resolve(__dirname, "..");
let mainWindow = null;
let backendClient = null;
let isQuitting = false;

protocol.registerSchemesAsPrivileged([
  {
    scheme: "memoframe-media",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
    },
  },
]);

const MIME_TYPES = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".bmp": "image/bmp",
  ".tif": "image/tiff",
  ".tiff": "image/tiff",
  ".svg": "image/svg+xml",
  ".mp4": "video/mp4",
  ".m4v": "video/mp4",
  ".webm": "video/webm",
  ".mov": "video/quicktime",
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
};

function registerMediaProtocol() {
  protocol.handle("memoframe-media", async request => {
    try {
      const parsed = new URL(request.url);
      const rawPath = parsed.searchParams.get("path");
      if (!rawPath) {
        return new Response("Missing path parameter", { status: 400 });
      }
      let resolved = path.resolve(rawPath);
      if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
        const repoRoot = path.resolve(APP_ROOT, "..", "..");
        const repoResolved = path.resolve(repoRoot, rawPath);
        if (fs.existsSync(repoResolved) && fs.statSync(repoResolved).isFile()) {
          resolved = repoResolved;
        } else {
          return new Response("Not found", { status: 404 });
        }
      }

      const ext = path.extname(resolved).toLowerCase();
      const contentType = MIME_TYPES[ext];
      if (!contentType) {
        return new Response("Unsupported media type", { status: 403 });
      }

      // Stream file asynchronously off-thread using Chromium's native net.fetch,
      // forwarding Range headers so HTML5 video/Live Photo seeking works cleanly.
      const fileUrl = pathToFileURL(resolved).toString();
      const fetchHeaders = {};
      const rangeHeader = request.headers.get("range");
      if (rangeHeader) fetchHeaders["Range"] = rangeHeader;

      const response = await net.fetch(fileUrl, { headers: fetchHeaders });
      const headers = new Headers(response.headers);
      headers.set("Content-Type", contentType);
      headers.set("Accept-Ranges", "bytes");
      if (!rangeHeader) {
        headers.set("Cache-Control", "public, max-age=31536000, immutable");
      }

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers,
      });
    } catch {
      return new Response("Bad request", { status: 400 });
    }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 820,
    minHeight: 540,
    title: "MemoFrame — Local Photo & Face Intelligence",
    icon: path.join(APP_ROOT, "public", process.platform === "win32" ? "logo.ico" : "logo.png"),
    backgroundColor: "#0f1216",
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    mainWindow.loadURL(devUrl);
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(APP_ROOT, "dist", "index.html"));
  }

  mainWindow.once("ready-to-show", () => mainWindow && mainWindow.show());

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    } else {
      createWindow();
    }
  });

  app.whenReady().then(() => {
    if (process.platform === "win32") app.setAppUserModelId("com.memoframe.desktop");
    registerMediaProtocol();
    backendClient = new BackendClient(APP_ROOT, (event, data) => {
      for (const win of BrowserWindow.getAllWindows()) {
        if (!win.isDestroyed()) {
          win.webContents.send("memoframe:event", { event, data });
        }
      }
    });
    backendClient.start();
    registerIpcHandlers(backendClient, () => mainWindow);
    createWindow();

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });

  app.on("before-quit", event => {
    if (isQuitting || !backendClient) return;
    isQuitting = true;
    event.preventDefault();
    backendClient.stop().finally(() => {
      app.exit(0);
    });
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });
}

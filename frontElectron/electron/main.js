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

protocol.registerSchemesAsPrivileged([
  {
    scheme: "memoframe-media",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
      bypassCSP: true,
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
  ".svg": "image/svg+xml",
  ".mp4": "video/mp4",
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
        return new Response("Missing path parameter", {
          status: 400,
          headers: { "Access-Control-Allow-Origin": "*" },
        });
      }
      let resolved = path.resolve(rawPath);
      if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
        // Fallback for paths relative to repository root
        const repoRoot = path.resolve(APP_ROOT, "..");
        const repoResolved = path.resolve(repoRoot, rawPath);
        if (fs.existsSync(repoResolved) && fs.statSync(repoResolved).isFile()) {
          resolved = repoResolved;
        } else {
          return new Response("Not found", {
            status: 404,
            headers: { "Access-Control-Allow-Origin": "*" },
          });
        }
      }

      const ext = path.extname(resolved).toLowerCase();
      const contentType = MIME_TYPES[ext] || "application/octet-stream";

      // Stream file asynchronously off-thread using Chromium's native net.fetch
      // This completely avoids blocking the Electron main UI event loop.
      const fileUrl = pathToFileURL(resolved).toString();
      const response = await net.fetch(fileUrl);
      const headers = new Headers(response.headers);
      headers.set("Content-Type", contentType);
      headers.set("Access-Control-Allow-Origin", "*");
      headers.set("Cache-Control", "public, max-age=31536000, immutable");

      return new Response(response.body, {
        status: 200,
        headers,
      });
    } catch (err) {
      return new Response("Bad request", {
        status: 400,
        headers: { "Access-Control-Allow-Origin": "*" },
      });
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

app.whenReady().then(() => {
  registerMediaProtocol();
  backendClient = new BackendClient(APP_ROOT, (event, data) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("memoframe:event", { event, data });
    }
  });
  backendClient.start();
  registerIpcHandlers(backendClient, () => mainWindow);
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  if (backendClient) backendClient.stop();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

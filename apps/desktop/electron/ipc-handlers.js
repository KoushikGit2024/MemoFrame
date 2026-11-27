"use strict";

const fs = require("fs");
const path = require("path");
const { dialog, ipcMain, shell } = require("electron");

function registerIpcHandlers(backendClient, getMainWindow) {
  ipcMain.handle("memoframe:rpc", async (_event, method, params) => {
    try {
      const result = await backendClient.call(String(method), params || {});
      return { ok: true, result };
    } catch (err) {
      return {
        ok: false,
        error: {
          code: err.code || "RPC_ERROR",
          message: err.message || String(err),
          hint: err.hint || "",
        },
      };
    }
  });

  ipcMain.handle("memoframe:select-folder", async () => {
    const win = getMainWindow();
    const res = await dialog.showOpenDialog(win || undefined, {
      title: "Select Photo Folder to Scan",
      properties: ["openDirectory"],
    });
    if (res.canceled || !res.filePaths.length) return null;
    return res.filePaths[0];
  });

  ipcMain.handle("memoframe:reveal-file", async (_event, targetPath) => {
    if (!targetPath) return false;
    const resolved = path.resolve(String(targetPath));
    if (fs.existsSync(resolved) && fs.statSync(resolved).isFile()) {
      shell.showItemInFolder(resolved);
      return true;
    }
    const parent = path.dirname(resolved);
    if (fs.existsSync(parent)) {
      await shell.openPath(parent);
      return true;
    }
    return false;
  });

  ipcMain.handle("memoframe:open-file", async (_event, targetPath) => {
    if (!targetPath) return false;
    const resolved = path.resolve(String(targetPath));
    if (fs.existsSync(resolved)) {
      const err = await shell.openPath(resolved);
      return !err;
    }
    return false;
  });

  ipcMain.handle("memoframe:open-lightbox-window", async (_event, photoId) => {
    const { BrowserWindow } = require("electron");
    const win = new BrowserWindow({
      width: 1180,
      height: 780,
      minWidth: 720,
      minHeight: 480,
      title: "MemoFrame — Photo Viewer",
      icon: path.join(__dirname, "..", "public", process.platform === "win32" ? "logo.ico" : "logo.png"),
      backgroundColor: "#0f1216",
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
      win.loadURL(`${devUrl}?lightbox=${encodeURIComponent(String(photoId))}`);
    } else {
      win.loadFile(path.join(__dirname, "..", "dist", "index.html"), {
        query: { lightbox: String(photoId) },
      });
    }
    return true;
  });
}

module.exports = { registerIpcHandlers };

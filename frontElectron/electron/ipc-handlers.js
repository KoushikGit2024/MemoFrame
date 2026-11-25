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
}

module.exports = { registerIpcHandlers };

"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("memoframe", {
  rpc: (method, params = {}) => ipcRenderer.invoke("memoframe:rpc", method, params),
  selectFolder: () => ipcRenderer.invoke("memoframe:select-folder"),
  revealFile: filePath => ipcRenderer.invoke("memoframe:reveal-file", filePath),
  openFile: filePath => ipcRenderer.invoke("memoframe:open-file", filePath),
  openLightboxWindow: photoId => ipcRenderer.invoke("memoframe:open-lightbox-window", photoId),
  onEvent: callback => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("memoframe:event", listener);
    return () => ipcRenderer.removeListener("memoframe:event", listener);
  },
  platform: process.platform,
});

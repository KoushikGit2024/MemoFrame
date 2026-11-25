'use strict';

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { app, BrowserWindow, net, protocol } = require('electron');

const { BackendClient } = require('./backend-client');
const { registerIpcHandlers } = require('./ipc-handlers');

const APP_ROOT = path.resolve(__dirname, '..');
let mainWindow = null;
let backendClient = null;

protocol.registerSchemesAsPrivileged([
  {
    scheme: 'memoframe-media',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,
    },
  },
]);

function registerMediaProtocol() {
  protocol.handle('memoframe-media', async (request) => {
    try {
      const parsed = new URL(request.url);
      const rawPath = parsed.searchParams.get('path');
      if (!rawPath) return new Response('Missing path parameter', { status: 400 });
      const resolved = path.resolve(rawPath);
      if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
        return new Response('Not found', { status: 404 });
      }
      return net.fetch(pathToFileURL(resolved).toString());
    } catch {
      return new Response('Bad request', { status: 400 });
    }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 820,
    minHeight: 540,
    title: 'MemoFrame — Local Photo & Face Intelligence',
    backgroundColor: '#0f1216',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    mainWindow.loadURL(devUrl);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(APP_ROOT, 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  registerMediaProtocol();
  backendClient = new BackendClient(APP_ROOT, (event, data) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('memoframe:event', { event, data });
    }
  });
  backendClient.start();
  registerIpcHandlers(backendClient, () => mainWindow);
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => {
  if (backendClient) backendClient.stop();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

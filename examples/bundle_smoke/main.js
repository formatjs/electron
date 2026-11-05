// SPDX-License-Identifier: MIT
const {app, BrowserWindow} = require('electron');
const fs = require('node:fs');
const path = require('node:path');

app.whenReady().then(async () => {
  const window = new BrowserWindow({
    width: 800, height: 600, show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      sandbox: false, contextIsolation: false, nodeIntegration: false,
      webviewTag: false,
    },
  });
  await window.loadFile(path.join(__dirname, 'index.html'));
  const result = await window.webContents.executeJavaScript('window.bundleCheck');
  if (result !== 'registered-and-guarded') throw new Error(`Bundle behavior failed: ${result}`);
  const image = await window.webContents.capturePage();
  if (image.isEmpty()) throw new Error('Bundle smoke rendered empty image');
  fs.writeFileSync(process.env.ELECTRON_SMOKE_OUTPUT, image.toPNG());
  console.log('Generated bundle registered native webview class; unattached access guarded');
  app.quit();
}).catch(error => {
  console.error(error);
  app.exit(1);
});

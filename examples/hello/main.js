// SPDX-License-Identifier: MIT
const {app, BrowserWindow} = require('electron');
const fs = require('node:fs');
const path = require('node:path');

app.whenReady().then(async () => {
  const window = new BrowserWindow({
    width: 800,
    height: 600,
    show: !process.env.ELECTRON_SMOKE_OUTPUT,
    webPreferences: {sandbox: true, contextIsolation: true, nodeIntegration: false},
  });
  await window.loadFile(path.join(__dirname, 'index.html'));
  if (process.env.ELECTRON_SMOKE_OUTPUT) {
    const result = await window.webContents.executeJavaScript('document.querySelector("h1").textContent');
    if (result !== 'Bazel Electron') throw new Error(`Unexpected rendered content: ${result}`);
    const image = await window.webContents.capturePage();
    if (image.isEmpty()) throw new Error('Empty screenshot');
    const bitmap = image.toBitmap();
    let background = 0;
    for (let offset = 0; offset < bitmap.length; offset += 4) {
      if (bitmap[offset] === 0x3d && bitmap[offset + 1] === 0x23 && bitmap[offset + 2] === 0x17) background++;
    }
    const ratio = background / (bitmap.length / 4);
    if (ratio < 0.2 || ratio > 0.995) throw new Error(`Unexpected rendered pixels: ${ratio}`);
    fs.writeFileSync(process.env.ELECTRON_SMOKE_OUTPUT, image.toPNG());
    app.quit();
  }
}).catch(error => {
  console.error(error);
  app.exit(1);
});
app.on('window-all-closed', () => app.quit());

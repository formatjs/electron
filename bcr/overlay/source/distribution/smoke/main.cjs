const {app, BrowserWindow, ipcMain} = require('electron');
const path = require('node:path');

setTimeout(() => app.exit(2), 45000).unref();
app.whenReady().then(async () => {
  ipcMain.handle('source-runtime-probe', (_event, value) => value + 2);
  const window = new BrowserWindow({
    width: 64,
    height: 64,
    useContentSize: true,
    frame: false,
    show: true,
    backgroundColor: '#ffffff',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });
  await window.loadFile(path.join(__dirname, 'index.html'));
  const renderer = await window.webContents.executeJavaScript(`(async () => ({
    answer: await window.runtimeProbe.ping(40),
    nodeIntegration: typeof process !== 'undefined' || typeof require !== 'undefined',
  }))()`);
  const image = await window.webContents.capturePage();
  const bitmap = image.toBitmap();
  if (image.isEmpty() || bitmap.length !== 64 * 64 * 4) throw new Error('Missing rendered pixels');
  console.log('SOURCE_RUNTIME_BROWSER_SMOKE:' + JSON.stringify({
    ...renderer,
    packaged: app.isPackaged,
    fromAsar: __dirname.endsWith(path.sep + 'app.asar'),
    size: image.getSize(),
    channels: Array.from(bitmap.subarray(0, 3)).sort((left, right) => left - right),
    alpha: bitmap[3],
  }));
  window.destroy();
  app.quit();
}).catch(error => {
  console.error(error);
  app.exit(1);
});

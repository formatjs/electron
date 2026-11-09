const {app, BrowserWindow, ipcMain} = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const originalFs = require('original-fs');
const path = require('node:path');

async function checkAsarAliases() {
  const archive = path.join(process.resourcesPath, 'links.asar');
  const canonical = path.join(archive, 'native/answer.cjs');
  const expected = 'module.exports = {answer: 42};\n';
  const module = require(canonical);
  assert.equal(module.answer, 42);
  for (const name of ['directory/answer.cjs', 'alias.cjs', 'chain.cjs', 'root/chain.cjs']) {
    const alias = path.join(archive, name);
    assert.equal(fs.readFileSync(alias, 'utf8'), expected);
    assert.equal(await fs.promises.readFile(alias, 'utf8'), expected);
    assert.equal(fs.realpathSync(alias), canonical);
    assert.equal(await fs.promises.realpath(alias), canonical);
    assert.equal(require(alias), module);
  }
  assert(fs.lstatSync(path.join(archive, 'chain.cjs')).isSymbolicLink());
  assert.deepEqual(fs.readdirSync(path.join(archive, 'directory')), ['answer.cjs']);
  assert.deepEqual(await fs.promises.readdir(path.join(archive, 'directory')), ['answer.cjs']);
  assert.throws(() => fs.readFileSync(path.join(archive, 'cycle-a')), {code: 'ENOENT'});

  const descriptors = ['packed.bin', 'packed-alias.bin'].map(name => fs.openSync(path.join(archive, name), 'r'));
  try {
    const [first, second] = descriptors.map(descriptor => fs.fstatSync(descriptor));
    assert.equal(first.dev, second.dev);
    assert.equal(first.ino, second.ino);
    assert.equal(fs.readFileSync(descriptors[1], 'utf8'), 'packed fixture\n');
  } finally {
    descriptors.forEach(descriptor => fs.closeSync(descriptor));
  }
  const descriptor = fs.openSync(path.join(archive, 'chain.cjs'), 'r+');
  const addition = Buffer.from('// alias write\n');
  try {
    fs.writeSync(descriptor, addition, 0, addition.length, Buffer.byteLength(expected));
  } finally {
    fs.closeSync(descriptor);
  }
  assert.equal(originalFs.readFileSync(archive + '.unpacked/native/answer.cjs', 'utf8'), expected + addition.toString('utf8'));
  assert(!originalFs.existsSync(archive + '.unpacked/chain.cjs'));
  assert(!originalFs.existsSync(archive + '.unpacked/directory'));
}

setTimeout(() => app.exit(2), 45000).unref();
app.whenReady().then(async () => {
  await checkAsarAliases();
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
  for (const name of ['home', 'appData', 'userData', 'sessionData']) {
    assert(path.isAbsolute(app.getPath(name)), `Expected absolute ${name} path`);
  }
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
    asarAliases: true,
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

const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('runtimeProbe', {
  ping: value => ipcRenderer.invoke('source-runtime-probe', value),
});

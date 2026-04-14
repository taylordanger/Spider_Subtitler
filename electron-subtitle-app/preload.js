const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('subtitleApp', {
  start: (config) => ipcRenderer.invoke('subtitle:start', config),
  stop: () => ipcRenderer.invoke('subtitle:stop'),
  onSubtitle: (handler) => ipcRenderer.on('subtitle:update', (_, text) => handler(text)),
  onStatus: (handler) => ipcRenderer.on('subtitle:status', (_, status) => handler(status)),
  onAudioLevel: (handler) => ipcRenderer.on('subtitle:audioLevel', (_, payload) => handler(payload)),
  onLog: (handler) => ipcRenderer.on('subtitle:log', (_, line) => handler(line))
  ,saveSession: (text) => ipcRenderer.invoke('subtitle:save', text)
  ,onClearRequest: (handler) => ipcRenderer.on('subtitle:clear', () => handler())
});

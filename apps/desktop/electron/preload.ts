import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  getServiceStatus: () => ipcRenderer.invoke('get-service-status'),
  getUserDataDir: () => ipcRenderer.invoke('get-user-data-dir'),
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),

  onServiceStatusChange: (callback: (status: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: unknown) => callback(status);
    ipcRenderer.on('service-status-changed', listener);
    return () => ipcRenderer.removeListener('service-status-changed', listener);
  },
});

declare global {
  interface Window {
    electronAPI: {
      getServiceStatus: () => Promise<{
        backend: { running: boolean; url?: string; pid?: number };
        frontend: { running: boolean; url?: string; pid?: number };
      }>;
      getUserDataDir: () => Promise<string>;
      openExternal: (url: string) => Promise<void>;
      onServiceStatusChange: (callback: (status: unknown) => void) => () => void;
    };
  }
}

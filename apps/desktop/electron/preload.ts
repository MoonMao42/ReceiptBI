import { contextBridge, ipcRenderer } from 'electron';
import { randomUUID } from 'node:crypto';
import type { DesktopAppInfo } from './app-info.js';
import {
  describeChunkLoadFailure,
  RENDERER_CHUNK_FAILURE_CHANNEL,
} from './frontend-reliability.js';

const rendererDocumentId = randomUUID();
let chunkFailureReported = false;

function reportChunkLoadFailure(reason: unknown): void {
  if (chunkFailureReported) return;
  const failure = describeChunkLoadFailure(reason);
  if (!failure) return;

  chunkFailureReported = true;
  ipcRenderer.send(RENDERER_CHUNK_FAILURE_CHANNEL, {
    ...failure,
    documentId: rendererDocumentId,
  });
}

window.addEventListener('error', (event) => {
  reportChunkLoadFailure(
    event.error ?? {
      name: 'Error',
      message: event.message,
    }
  );
});

window.addEventListener('unhandledrejection', (event) => {
  reportChunkLoadFailure(event.reason);
});

contextBridge.exposeInMainWorld('electronAPI', {
  getServiceStatus: () => ipcRenderer.invoke('get-service-status'),
  getUserDataDir: () => ipcRenderer.invoke('get-user-data-dir'),
  getAppInfo: (): Promise<DesktopAppInfo> => ipcRenderer.invoke('get-app-info'),
  quitApp: () => ipcRenderer.send('quit-app'),
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),

  onServiceStatusChange: (callback: (status: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: unknown) => callback(status);
    ipcRenderer.on('service-status-changed', listener);
    return () => ipcRenderer.removeListener('service-status-changed', listener);
  },
});

declare global {
  interface Window {
    electronAPI?: {
      getServiceStatus: () => Promise<{
        backend: { running: boolean; url?: string; pid?: number };
        frontend: { running: boolean; url?: string; pid?: number };
      }>;
      getUserDataDir: () => Promise<string>;
      getAppInfo?: () => Promise<DesktopAppInfo>;
      quitApp?: () => void;
      openExternal: (url: string) => Promise<void>;
      onServiceStatusChange: (callback: (status: unknown) => void) => () => void;
    };
  }
}

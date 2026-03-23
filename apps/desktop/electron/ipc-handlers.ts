import type { IpcMain } from 'electron';
import { shell } from 'electron';
import path from 'node:path';
import os from 'node:os';
import type { ProcessManager } from './process-manager.js';
import type { Logger } from './logger.js';

export function registerIpcHandlers(
  ipcMain: IpcMain,
  processManager: ProcessManager,
  logger: Logger
): void {
  ipcMain.handle('get-service-status', () => processManager.getStatus());
  ipcMain.handle('get-user-data-dir', () => processManager.getUserDataDir());

  ipcMain.handle('open-external', async (_event, url: string) => {
    logger.info(`Opening external URL: ${url}`);
    await shell.openExternal(url);
  });

  // 每 10 秒广播一次服务状态
  setInterval(() => {
    const status = processManager.getStatus();
    const { BrowserWindow } = require('electron');
    BrowserWindow.getAllWindows().forEach((win: Electron.BrowserWindow) => {
      win.webContents.send('service-status-changed', status);
    });
  }, 10000);

  logger.info('IPC handlers registered');
}

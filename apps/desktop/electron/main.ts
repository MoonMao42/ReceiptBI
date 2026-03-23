import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'node:path';
import { ProcessManager } from './process-manager.js';
import { registerIpcHandlers } from './ipc-handlers.js';
import { setupLogger } from './logger.js';

const logger = setupLogger();
let mainWindow: BrowserWindow | null = null;
let processManager: ProcessManager;

const isDev = process.env.NODE_ENV === 'development';

async function createWindow(): Promise<BrowserWindow> {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: 'QueryGPT',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
    show: false,
  });

  win.once('ready-to-show', () => {
    win.show();
    logger.info('Main window shown');
  });

  return win;
}

app.whenReady().then(async () => {
  logger.info('QueryGPT Desktop starting...');

  processManager = new ProcessManager(logger);
  registerIpcHandlers(ipcMain, processManager, logger);

  mainWindow = await createWindow();

  try {
    await processManager.startAll();

    const frontendUrl = processManager.getFrontendUrl();
    await mainWindow.loadURL(frontendUrl);
    logger.info(`Frontend loaded: ${frontendUrl}`);
  } catch (error) {
    logger.error('Failed to start services', error);
    // 显示错误页面而不是直接退出
    mainWindow.show();
    mainWindow.loadURL(`data:text/html,
      <html><body style="font-family:system-ui;padding:40px;background:#1a1a2e;color:#eee">
      <h1>QueryGPT 启动失败</h1>
      <p>服务未能正常启动，请检查日志：</p>
      <code style="color:#ff6b6b">${String(error).replace(/</g,'&lt;')}</code>
      <p style="margin-top:20px;color:#888">日志位置: ~/.querygpt-desktop/logs/</p>
      </body></html>`);
  }

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = await createWindow();
      try {
        await processManager.startAll();
        await mainWindow.loadURL(processManager.getFrontendUrl());
      } catch (err) {
        logger.error('Failed to restart services on activate', err);
        app.quit();
      }
    }
  });
});

app.on('before-quit', async () => {
  logger.info('Application quitting...');
  await processManager?.stopAll();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

process.on('uncaughtException', (error) => {
  logger.error('Uncaught exception', error);
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  logger.error('Unhandled rejection', reason);
});

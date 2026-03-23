import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'node:path';
import { ProcessManager } from './process-manager.js';
import { registerIpcHandlers } from './ipc-handlers.js';
import { setupLogger } from './logger.js';

const logger = setupLogger();
let mainWindow: BrowserWindow | null = null;
let processManager: ProcessManager;

const isDev = process.env.NODE_ENV === 'development';

const LOADING_HTML = `data:text/html;charset=utf-8,${encodeURIComponent(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { margin:0; height:100vh; display:flex; align-items:center; justify-content:center;
         background:#0f0f1a; color:#e0e0e0; font-family:system-ui,-apple-system,sans-serif; }
  .wrap { text-align:center; }
  .spinner { width:40px; height:40px; margin:0 auto 24px; border:3px solid #333;
             border-top-color:#6366f1; border-radius:50%; animation:spin .8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  h2 { font-size:18px; font-weight:500; margin:0 0 8px; }
  p { font-size:13px; color:#888; margin:0; }
</style></head><body>
<div class="wrap">
  <div class="spinner"></div>
  <h2>QueryGPT</h2>
  <p>Starting services...</p>
</div>
</body></html>`)}`;

const ERROR_HTML = (error: unknown) =>
  `data:text/html;charset=utf-8,${encodeURIComponent(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { margin:0; padding:40px; background:#0f0f1a; color:#e0e0e0; font-family:system-ui; }
  code { color:#ff6b6b; display:block; margin:12px 0; white-space:pre-wrap; }
  p { color:#888; }
</style></head><body>
<h1>QueryGPT failed to start</h1>
<p>Check the logs for details:</p>
<code>${String(error)}</code>
<p>Logs: ~/.querygpt-desktop/logs/</p>
</body></html>`)}`;

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
    backgroundColor: '#0f0f1a',
  });

  // 立即显示 loading 页面
  await win.loadURL(LOADING_HTML);
  win.show();
  logger.info('Loading screen shown');

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
    await mainWindow.loadURL(ERROR_HTML(error));
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

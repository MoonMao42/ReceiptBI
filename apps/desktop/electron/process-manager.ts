import { spawn, execSync, type ChildProcess } from 'node:child_process';
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs';
import { app, utilityProcess, type UtilityProcess } from 'electron';
import type { Logger } from './logger.js';

export interface ServiceStatus {
  name: string;
  running: boolean;
  pid?: number;
  url?: string;
  error?: string;
}

// 固定端口
const BACKEND_PORT = 18080;
const FRONTEND_PORT = 13000;

export class ProcessManager {
  private backendProcess: ChildProcess | null = null;
  private frontendProcess: UtilityProcess | ChildProcess | null = null;
  private readonly logger: Logger;
  private readonly baseDir: string;
  private readonly userDataDir: string;

  constructor(logger: Logger) {
    this.logger = logger;
    this.baseDir = this.getResourceBaseDir();
    this.userDataDir = path.join(os.homedir(), '.querygpt-desktop');
  }

  private getResourceBaseDir(): string {
    if (!app.isPackaged) {
      return path.resolve(__dirname, '../../..');
    }
    return path.join(process.resourcesPath);
  }

  private getApiDir(): string {
    return path.join(this.baseDir, 'apps', 'api');
  }

  private getWebDir(): string {
    return path.join(this.baseDir, 'apps', 'web');
  }

  private getBackendOutDir(): string {
    return path.join(this.baseDir, 'backend');
  }

  private getNextOutDir(): string {
    return path.join(this.baseDir, 'next');
  }

  /** 杀掉占用指定端口的进程 */
  private killPortProcess(port: number): void {
    try {
      let cmd: string;
      if (process.platform === 'win32') {
        // Use cmd+netstat instead of PowerShell to avoid 1-2s cold start delay
        cmd = `cmd /c "netstat -ano | findstr :${port} | findstr LISTENING"`;
      } else {
        cmd = `lsof -ti tcp:${port}`;
      }
      const result = execSync(cmd, { encoding: 'utf-8', timeout: 3000 }).trim();
      if (result) {
        const pids = new Set<number>();
        for (const line of result.split('\n')) {
          if (process.platform === 'win32') {
            // netstat -ano output: "  TCP  0.0.0.0:18080  0.0.0.0:0  LISTENING  1234"
            const parts = line.trim().split(/\s+/);
            const p = parseInt(parts[parts.length - 1]);
            if (p > 0) pids.add(p);
          } else {
            const p = parseInt(line.trim());
            if (p > 0) pids.add(p);
          }
        }
        for (const p of pids) {
          try {
            if (process.platform === 'win32') {
              execSync(`taskkill /PID ${p} /F`, { encoding: 'utf-8' });
            } else {
              process.kill(p, 'SIGKILL');
            }
            this.logger.info(`Killed stale process ${p} on port ${port}`);
          } catch { /* already dead */ }
        }
      }
    } catch { /* no process on port */ }
  }

  /** 首次启动时从打包资源复制预生成的数据库到用户数据目录 */
  private copyBundledDatabases(): void {
    const dataDir = path.join(this.userDataDir, 'data');
    // 打包资源中的 data/ 目录（由 PyInstaller 打包进 backend/_internal/data/）
    const bundledDataDir = path.join(this.getBackendOutDir(), '_internal', 'data');

    for (const dbName of ['demo.db', 'querygpt.db']) {
      const dest = path.join(dataDir, dbName);
      if (fs.existsSync(dest)) continue;

      const src = path.join(bundledDataDir, dbName);
      if (fs.existsSync(src)) {
        fs.copyFileSync(src, dest);
        this.logger.info(`Copied bundled ${dbName} to user data dir`);
      }
    }
  }

  async startAll(): Promise<void> {
    fs.mkdirSync(this.userDataDir, { recursive: true });
    fs.mkdirSync(path.join(this.userDataDir, 'logs'), { recursive: true });
    fs.mkdirSync(path.join(this.userDataDir, 'data'), { recursive: true });

    const userEnv = path.join(this.userDataDir, '.env');
    const backendEnvExample = path.join(this.getBackendOutDir(), '.env.example');
    if (!fs.existsSync(userEnv) && fs.existsSync(backendEnvExample)) {
      fs.copyFileSync(backendEnvExample, userEnv);
      this.logger.info('Created user .env from example');
    }

    // 首次启动：从打包资源复制预生成的数据库到用户目录
    this.copyBundledDatabases();

    // 清理可能残留的旧进程
    this.killPortProcess(BACKEND_PORT);
    this.killPortProcess(FRONTEND_PORT);

    this.startBackend();
    this.startFrontend();
    await this.waitForServices();
  }

  private startBackend(): void {
    const apiDir = this.getApiDir();
    const backendDir = this.getBackendOutDir();
    const isPacked = fs.existsSync(backendDir);

    let exePath: string;
    let args: string[] = [];
    let cwd: string;

    if (isPacked) {
      const exeName = process.platform === 'win32' ? 'querygpt-api.exe' : 'querygpt-api';
      exePath = path.join(backendDir, exeName);
      cwd = backendDir;
      if (!fs.existsSync(exePath)) {
        throw new Error(`Backend executable not found: ${exePath}`);
      }
    } else {
      cwd = apiDir;
      exePath = process.platform === 'win32' ? 'python.exe' : 'python3';
      args = ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)];
    }

    this.logger.info(`Starting backend: ${exePath} ${args.join(' ')}`);

    const dataDir = path.join(this.userDataDir, 'data');
    const dbPath = path.join(dataDir, 'querygpt.db');

    const env = {
      ...process.env,
      HOST: '127.0.0.1',
      PORT: String(BACKEND_PORT),
      ENVIRONMENT: 'development',
      CORS_ORIGINS_STR: `http://127.0.0.1:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}`,
      DATA_DIR: dataDir,
      METADATA_DB_PATH: path.join(dataDir, 'metadata.db'),
      DATABASE_URL: `sqlite+aiosqlite:///${dbPath}`,
      QUERYGPT_ENV_FILE: path.join(this.userDataDir, '.env'),
    };

    if (isPacked && process.platform === 'linux') {
      (env as NodeJS.ProcessEnv).MPLBACKEND = 'Agg';
    }

    this.backendProcess = spawn(exePath, args, {
      cwd,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: false,
    });

    this.backendProcess.stdout?.on('data', (data) => {
      this.logger.debug(`[Backend] ${data.toString().trim()}`);
    });

    this.backendProcess.stderr?.on('data', (data) => {
      this.logger.debug(`[Backend] ${data.toString().trim()}`);
    });

    this.backendProcess.on('error', (error) => {
      this.logger.error('Backend process error', error);
    });

    this.backendProcess.on('exit', (code) => {
      if (code !== 0 && code !== null) {
        this.logger.warn(`Backend exited with code ${code}`);
      }
    });
  }

  private startFrontend(): void {
    const webDir = this.getWebDir();
    const nextDir = this.getNextOutDir();
    const serverJs = path.join(nextDir, 'server.js');
    const usePacked = fs.existsSync(serverJs);

    const env: Record<string, string> = {
      NEXT_PUBLIC_API_URL: `http://127.0.0.1:${BACKEND_PORT}`,
      PORT: String(FRONTEND_PORT),
      HOSTNAME: '127.0.0.1',
      NODE_ENV: 'production',
    };

    if (usePacked) {
      this.logger.info(`Starting frontend (utilityProcess): ${serverJs}`);
      const up = utilityProcess.fork(serverJs, [], {
        cwd: nextDir,
        env: { ...process.env, ...env },
        stdio: 'pipe',
      });
      up.stdout?.on('data', (data: Buffer) => {
        this.logger.debug(`[Frontend] ${data.toString().trim()}`);
      });
      up.stderr?.on('data', (data: Buffer) => {
        this.logger.debug(`[Frontend] ${data.toString().trim()}`);
      });
      up.on('exit', (code) => {
        if (code !== 0) {
          this.logger.warn(`Frontend exited with code ${code}`);
        }
      });
      this.frontendProcess = up as unknown as ChildProcess;
    } else {
      // 开发模式：用 next start
      this.logger.info('Starting frontend (dev mode): next start');
      const nextExe = process.platform === 'win32' ? 'next.cmd' : 'next';

      const devProc = spawn(nextExe, ['start', '-p', String(FRONTEND_PORT)], {
        cwd: webDir,
        env: { ...process.env, ...env },
        stdio: ['ignore', 'pipe', 'pipe'],
        detached: false,
      });

      devProc.stdout?.on('data', (data) => {
        this.logger.debug(`[Frontend] ${data.toString().trim()}`);
      });
      devProc.stderr?.on('data', (data) => {
        this.logger.debug(`[Frontend] ${data.toString().trim()}`);
      });
      devProc.on('error', (error) => {
        this.logger.error('Frontend process error', error);
      });
      devProc.on('exit', (code) => {
        if (code !== 0 && code !== null) {
          this.logger.warn(`Frontend exited with code ${code}`);
        }
      });

      this.frontendProcess = devProc;
    }
  }

  private async waitForServices(): Promise<void> {
    const http = await import('node:http');
    const maxAttempts = 60;
    const delay = 500;

    // 等待后端
    for (let i = 0; i < maxAttempts; i++) {
      try {
        await this.checkHttp(`http://127.0.0.1:${BACKEND_PORT}/health`, http);
        this.logger.info('Backend is ready');
        break;
      } catch {
        if (i === maxAttempts - 1) throw new Error('Backend failed to start');
        await new Promise((r) => setTimeout(r, delay));
      }
    }

    // 等待前端
    for (let i = 0; i < maxAttempts; i++) {
      try {
        await this.checkHttp(`http://127.0.0.1:${FRONTEND_PORT}`, http);
        this.logger.info('Frontend is ready');
        break;
      } catch {
        if (i === maxAttempts - 1) throw new Error('Frontend failed to start');
        await new Promise((r) => setTimeout(r, delay));
      }
    }
  }

  private checkHttp(url: string, http: typeof import('node:http')): Promise<void> {
    return new Promise((resolve, reject) => {
      const req = http.get(url, { timeout: 2000 }, () => resolve());
      req.on('error', reject);
      req.on('timeout', () => {
        req.destroy();
        reject(new Error('Timeout'));
      });
    });
  }

  async stopAll(): Promise<void> {
    this.logger.info('Stopping all services...');

    // 停止前端 (可能是 UtilityProcess 或 ChildProcess)
    if (this.frontendProcess) {
      this.frontendProcess.kill();
      await new Promise((r) => setTimeout(r, 500));
    }

    // 停止后端
    if (this.backendProcess) {
      this.backendProcess.kill('SIGTERM');
      await new Promise((r) => setTimeout(r, 1000));
      if (!this.backendProcess.killed) this.backendProcess.kill('SIGKILL');
    }

    this.frontendProcess = null;
    this.backendProcess = null;

    // 确保端口释放
    this.killPortProcess(BACKEND_PORT);
    this.killPortProcess(FRONTEND_PORT);

    this.logger.info('All services stopped');
  }

  getStatus(): { backend: ServiceStatus; frontend: ServiceStatus } {
    return {
      backend: {
        name: 'Backend (Python API)',
        running: this.backendProcess !== null && this.backendProcess.killed === false,
        pid: this.backendProcess?.pid,
        url: `http://127.0.0.1:${BACKEND_PORT}`,
      },
      frontend: {
        name: 'Frontend (Next.js)',
        running: this.frontendProcess !== null,
        pid: (this.frontendProcess as ChildProcess)?.pid,
        url: `http://127.0.0.1:${FRONTEND_PORT}`,
      },
    };
  }

  getFrontendUrl(): string {
    return `http://127.0.0.1:${FRONTEND_PORT}`;
  }

  getUserDataDir(): string {
    return this.userDataDir;
  }
}

#!/usr/bin/env tsx
/**
 * 构建 Next.js 前端 (standalone 模式)
 *
 * 流程:
 * 1. 设置 NEXT_PUBLIC_API_URL 为桌面版后端端口
 * 2. 运行 next build (output: 'standalone')
 * 3. 复制 standalone 产物到 apps/desktop/next/
 */

import { existsSync, mkdirSync, cpSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';

const ROOT = resolve(__dirname, '../../..');
const WEB_DIR = join(ROOT, 'apps/web');
const NEXT_OUT = join(ROOT, 'apps/desktop', 'next');

const BACKEND_PORT = 18080;

async function main() {
  console.log('=== Building Next.js Frontend (standalone) ===\n');

  // 1. 构建 Next.js
  console.log('[1/2] Running next build...');
  const { spawn } = await import('node:child_process');

  await new Promise<void>((resolve, reject) => {
    const proc = spawn('npx', ['next', 'build'], {
      cwd: WEB_DIR,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: `http://127.0.0.1:${BACKEND_PORT}`,
        NEXT_PUBLIC_APP_MODE: 'desktop',
        NODE_ENV: 'production',
      },
      stdio: 'inherit',
      shell: true,
    });
    proc.on('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`next build failed with code ${code}`));
    });
    proc.on('error', reject);
  });

  // 2. 复制 standalone 产物
  console.log('\n[2/2] Copying standalone output...');
  if (existsSync(NEXT_OUT)) rmSync(NEXT_OUT, { recursive: true });
  mkdirSync(NEXT_OUT, { recursive: true });

  // standalone server.js 和 node_modules
  const standaloneDir = join(WEB_DIR, '.next/standalone');
  // standalone 会把整个 monorepo 结构复制过来，实际的 app 在 standalone/apps/web/
  const standaloneWebDir = join(standaloneDir, 'apps/web');

  if (!existsSync(standaloneDir)) {
    throw new Error('Standalone output not found. Make sure next.config.ts has output: "standalone"');
  }

  // 复制 standalone 的 server.js 和 node_modules
  if (existsSync(standaloneWebDir)) {
    // monorepo 结构：standalone/apps/web/server.js
    cpSync(standaloneWebDir, NEXT_OUT, { recursive: true });
    // 也需要复制 standalone 根目录的 node_modules（共享依赖）
    const standaloneNodeModules = join(standaloneDir, 'node_modules');
    if (existsSync(standaloneNodeModules)) {
      cpSync(standaloneNodeModules, join(NEXT_OUT, 'node_modules'), { recursive: true });
    }
  } else {
    // 非 monorepo：standalone/server.js
    cpSync(standaloneDir, NEXT_OUT, { recursive: true });
  }

  // 复制静态文件（standalone 不包含 static 和 public）
  const staticSrc = join(WEB_DIR, '.next/static');
  const staticDest = join(NEXT_OUT, '.next/static');
  if (existsSync(staticSrc)) {
    mkdirSync(staticDest, { recursive: true });
    cpSync(staticSrc, staticDest, { recursive: true });
  }

  const publicSrc = join(WEB_DIR, 'public');
  const publicDest = join(NEXT_OUT, 'public');
  if (existsSync(publicSrc)) {
    mkdirSync(publicDest, { recursive: true });
    cpSync(publicSrc, publicDest, { recursive: true });
  }

  console.log(`\n✓ Frontend built at: ${NEXT_OUT}`);
}

main().catch((err) => {
  console.error('Build failed:', err);
  process.exit(1);
});

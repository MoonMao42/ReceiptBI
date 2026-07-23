#!/usr/bin/env tsx
/**
 * 构建 Next.js 前端 (standalone 模式)
 *
 * 流程:
 * 1. 设置 NEXT_PUBLIC_API_URL 为桌面版后端端口
 * 2. 在独立于 next dev 的目录运行 next build (output: 'standalone')
 * 3. 校验并原子发布 standalone 产物到 apps/desktop/next/
 */

import { cpSync, existsSync, mkdirSync, renameSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import {
  FRONTEND_NEXT_DIST_DIRECTORY,
  validateFrontendBundle,
  writeFrontendBuildManifest,
} from '../electron/frontend-bundle.js';

const ROOT = resolve(__dirname, '../../..');
const WEB_DIR = join(ROOT, 'apps/web');
const DESKTOP_DIR = join(ROOT, 'apps/desktop');
const NEXT_OUT = join(DESKTOP_DIR, 'next');
const NEXT_STAGING = join(DESKTOP_DIR, 'next.staging');
const NEXT_DIST_DIR = FRONTEND_NEXT_DIST_DIRECTORY;
const NEXT_BUILD_OUT = join(WEB_DIR, NEXT_DIST_DIR);

const BACKEND_PORT = 18080;

async function main() {
  console.log('=== Building Next.js Frontend (standalone) ===\n');

  // Fail closed: once a packaging build starts, an earlier desktop bundle is
  // no longer valid input. A failed build must leave no stale `next/` for a
  // later electron-builder invocation to pick up accidentally.
  rmSync(NEXT_OUT, { recursive: true, force: true });
  rmSync(NEXT_STAGING, { recursive: true, force: true });
  rmSync(NEXT_BUILD_OUT, { recursive: true, force: true });

  // 1. 构建 Next.js
  console.log('[1/2] Running next build...');
  const { spawn } = await import('node:child_process');
  const nextExecutable = join(
    WEB_DIR,
    'node_modules',
    '.bin',
    process.platform === 'win32' ? 'next.cmd' : 'next'
  );
  if (!existsSync(nextExecutable)) {
    throw new Error(`Next.js executable not found: ${nextExecutable}`);
  }

  await new Promise<void>((resolve, reject) => {
    const proc = spawn(nextExecutable, ['build'], {
      cwd: WEB_DIR,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: `http://127.0.0.1:${BACKEND_PORT}`,
        NEXT_PUBLIC_APP_MODE: 'desktop',
        RECEIPTBI_NEXT_DIST_DIR: NEXT_DIST_DIR,
        NODE_ENV: 'production',
      },
      stdio: 'inherit',
      shell: process.platform === 'win32',
    });
    proc.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`next build failed with code ${code}`));
    });
    proc.on('error', reject);
  });

  // 2. 复制 standalone 产物
  console.log('\n[2/2] Copying standalone output...');
  mkdirSync(NEXT_STAGING, { recursive: true });

  // standalone server.js 和 node_modules
  const standaloneDir = join(NEXT_BUILD_OUT, 'standalone');
  // standalone 会把整个 monorepo 结构复制过来，实际的 app 在 standalone/apps/web/
  const standaloneWebDir = join(standaloneDir, 'apps/web');

  if (!existsSync(standaloneDir)) {
    throw new Error('Standalone output not found. Make sure next.config.ts has output: "standalone"');
  }

  // 复制 standalone 的 server.js 和 node_modules
  if (existsSync(standaloneWebDir)) {
    // monorepo 结构：standalone/apps/web/server.js
    cpSync(standaloneWebDir, NEXT_STAGING, { recursive: true });
    // 也需要复制 standalone 根目录的 node_modules（共享依赖）
    const standaloneNodeModules = join(standaloneDir, 'node_modules');
    if (existsSync(standaloneNodeModules)) {
      cpSync(standaloneNodeModules, join(NEXT_STAGING, 'node_modules'), { recursive: true });
    }
  } else {
    // 非 monorepo：standalone/server.js
    cpSync(standaloneDir, NEXT_STAGING, { recursive: true });
  }

  // 复制静态文件（standalone 不包含 static 和 public）
  const staticSrc = join(NEXT_BUILD_OUT, 'static');
  const staticDest = join(NEXT_STAGING, NEXT_DIST_DIR, 'static');
  if (!existsSync(staticSrc)) throw new Error(`Next.js static output not found: ${staticSrc}`);
  mkdirSync(staticDest, { recursive: true });
  cpSync(staticSrc, staticDest, { recursive: true });

  const publicSrc = join(WEB_DIR, 'public');
  const publicDest = join(NEXT_STAGING, 'public');
  if (existsSync(publicSrc)) {
    mkdirSync(publicDest, { recursive: true });
    cpSync(publicSrc, publicDest, { recursive: true });
  }

  const manifest = writeFrontendBuildManifest(NEXT_STAGING);
  validateFrontendBundle(NEXT_STAGING);
  renameSync(NEXT_STAGING, NEXT_OUT);
  console.log(`\n✓ Frontend build ${manifest.buildId} published at: ${NEXT_OUT}`);
}

main().catch((err) => {
  rmSync(NEXT_STAGING, { recursive: true, force: true });
  console.error('Build failed:', err);
  process.exit(1);
});

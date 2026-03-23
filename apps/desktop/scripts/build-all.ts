#!/usr/bin/env tsx
/**
 * 一键构建脚本
 *
 * 依次执行:
 * 1. TypeScript 编译 Electron 主进程
 * 2. 构建 Python 后端 (PyInstaller)
 * 3. 构建 Next.js 前端
 */

import { execSync } from 'node:child_process';
import { resolve } from 'node:path';

const DESKTOP_DIR = resolve(__dirname, '..');

function run(cmd: string, cwd?: string) {
  console.log(`$ ${cmd}\n`);
  execSync(cmd, {
    cwd: cwd ?? DESKTOP_DIR,
    stdio: 'inherit',
    encoding: 'utf-8',
    env: process.env,
    shell: '/bin/bash',
  });
}

async function main() {
  console.log('=== QueryGPT Desktop Build ===\n');

  // 1. TypeScript 编译
  console.log('[1/3] Building Electron main process...');
  run('npx tsc -p tsconfig.electron.json');

  // 2. 构建 Python 后端
  console.log('\n[2/3] Building Python backend (PyInstaller)...');
  run('npx tsx scripts/build-pyinstaller.ts');

  // 3. 构建 Next.js 前端
  console.log('\n[3/3] Building Next.js frontend...');
  run('npx tsx scripts/build-next.ts');

  console.log('\n=== Build Complete ===');
  console.log('Next steps:');
  console.log('  macOS:  npm run build:electron:mac');
  console.log('  Windows: npm run build:electron:win');
  console.log('  Both:    npm run build:electron');
}

main().catch((err) => {
  console.error('Build failed:', err);
  process.exit(1);
});

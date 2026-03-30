#!/usr/bin/env tsx
/**
 * 构建 Python 后端 (PyInstaller --onedir)
 *
 * 流程:
 * 1. 从 apps/api 生成 requirements.txt
 * 2. 创建临时 venv 并安装依赖
 * 3. 生成 PyInstaller spec 文件
 * 4. 运行 PyInstaller 打包
 * 5. 复制输出到 apps/desktop/backend/
 */

import { execSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync, copyFileSync, cpSync, rmSync, readlinkSync, symlinkSync, lstatSync } from 'node:fs';
import { join, resolve, dirname, relative } from 'node:path';

const ROOT = resolve(__dirname, '../../..');
const API_DIR = join(ROOT, 'apps/api');
const DESKTOP_DIR = join(ROOT, 'apps/desktop');
const BUILD_DIR = join(DESKTOP_DIR, 'build');
const BACKEND_OUT = join(DESKTOP_DIR, 'backend');

function run(cmd: string, opts?: { cwd?: string; stdio?: 'inherit' | 'pipe' }) {
  console.log(`  $ ${cmd}`);
  execSync(cmd, {
    cwd: opts?.cwd ?? ROOT,
    stdio: opts?.stdio ?? 'inherit',
    encoding: 'utf-8',
    env: process.env,
    shell: true,
  });
}

function fixSymlinks(dir: string) {
  const { readdirSync, lstatSync, existsSync, copyFileSync, unlinkSync, readlinkSync, symlinkSync } = require('node:fs');
  const entries = readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== 'node_modules') fixSymlinks(full);
    } else if (entry.isSymbolicLink()) {
      const target = readlinkSync(full);
      if (target.startsWith('/')) {
        const dirOfLink = dirname(full);
        const resolved = resolve(dirOfLink, target);
        if (existsSync(resolved)) {
          if (lstatSync(resolved).isDirectory()) {
            // 目录符号链接：绝对路径转为相对路径
            unlinkSync(full);
            const rel = relative(dirOfLink, resolved);
            symlinkSync(rel, full);
            console.log(`  Fixed dir symlink: ${entry.name} -> ${rel}`);
          } else {
            unlinkSync(full);
            copyFileSync(resolved, full);
            console.log(`  Replaced symlink with file: ${entry.name}`);
          }
        } else {
          console.warn(`  Warning: symlink target not found: ${target}`);
          unlinkSync(full);
          const rel = relative(dirOfLink, resolved);
          symlinkSync(rel, full);
          console.log(`  Fixed symlink (target missing): ${entry.name} -> ${rel}`);
        }
      }
    }
  }
}

async function main() {
  console.log('=== Building Python Backend ===\n');

  mkdirSync(BUILD_DIR, { recursive: true });
  mkdirSync(BACKEND_OUT, { recursive: true });

  // 1. 生成 requirements.txt
  console.log('[1/5] Generating requirements.txt...');
  const apiVenvPip = join(API_DIR, '.venv', process.platform === 'win32' ? 'Scripts/pip.exe' : 'bin/pip');
  let requirements: string;
  if (existsSync(apiVenvPip)) {
    requirements = execSync(`"${apiVenvPip}" freeze`, { encoding: 'utf-8', cwd: API_DIR });
  } else {
    requirements = execSync('uv pip freeze', { encoding: 'utf-8', cwd: API_DIR });
  }
  // 过滤掉 git 来源的包（如 querygpt_api），PyInstaller 通过 desktop-entry.py 直接导入 app.main
  const frozenPkgs = requirements.split('\n').filter((line) => {
    const l = line.trim();
    return l && !l.startsWith('git+') && !l.startsWith('-e ') && !l.startsWith('#');
  }).join('\n');
  writeFileSync(join(BUILD_DIR, 'requirements.txt'), frozenPkgs);

  // 2. 创建 build venv（使用 Python 3.13，PyInstaller 6.19.0 需要）
  console.log('\n[2/5] Creating build venv with Python 3.13...');
  const venvDir = join(BUILD_DIR, '.build-venv');
  if (existsSync(venvDir)) rmSync(venvDir, { recursive: true });
  let pythonBin: string;
  if (process.platform === 'win32') {
    pythonBin = execSync('where python', { encoding: 'utf-8' }).trim().split('\n')[0].trim();
  } else {
    pythonBin = execSync('which python3.13 || which python3', { encoding: 'utf-8' }).trim();
  }

  // Try uv first (handles uv-installed Python where ensurepip fails), fall back to stdlib venv
  const hasUv = (() => { try { execSync('which uv', { encoding: 'utf-8' }); return true; } catch { return false; } })();
  if (hasUv) {
    run(`uv venv ${venvDir} --python ${pythonBin}`);
  } else {
    run(`${pythonBin} -m venv ${venvDir}`);
  }

  const python = join(venvDir, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python3');

  // Use uv pip if available (faster + works without pip in venv), fall back to venv pip
  const pip = join(venvDir, process.platform === 'win32' ? 'Scripts/pip.exe' : 'bin/pip');
  const pipInstall = (pkg: string) => {
    if (hasUv) {
      run(`uv pip install --python ${python} ${pkg}`);
    } else {
      run(`${pip} install ${pkg}`);
    }
  };

  // 安装 pyinstaller 和依赖
  console.log('Installing PyInstaller and dependencies...');
  pipInstall('pyinstaller==6.19.0');
  pipInstall(`-r ${join(BUILD_DIR, 'requirements.txt')}`);
  // 显式安装 aiosqlite（pydantic-settings 动态加载时需要）
  pipInstall('aiosqlite');

  // 2.5. 预生成 demo.db + querygpt.db（构建时生成，运行时直接复制到用户目录）
  console.log('\nPre-generating databases...');
  const seedScript = join(DESKTOP_DIR, 'scripts', 'seed-databases.py');
  run(`${python} "${seedScript}"`);

  // 3. 收集可能动态导入的模块
  console.log('\n[3/5] Collecting dynamic imports...');
  const hiddenImports = [
    'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.on',
    'fastapi', 'fastapi.applications', 'fastapi.routing',
    'pydantic', 'pydantic_settings', 'pydantic_extra_types.phone_numbers',
    'sqlalchemy', 'sqlalchemy.ext', 'sqlalchemy.ext.asyncio',
    'aiosqlite', 'sqlalchemy.dialects.sqlite.aiosqlite', 'sqlalchemy.dialects.sqlite',
    'litellm', 'litellm.main', 'litellm.llms', 'litellm.llms.openai',
    'pandas', 'numpy', 'matplotlib', 'matplotlib.backends.backend_agg',
    'slowapi', 'httpx', 'structlog', 'cryptography', 'alembic',
    'sse_starlette', 'asyncpg', 'pymysql', 'psycopg2',
    'charset_normalizer', 'idna', 'certifi', 'urllib3', 'jinja2',
    'python_multipart', 'python_dotenv', 'email_validator',
    'click', 'anyio', 'sniffio',
    'tiktoken', 'tiktoken_ext', 'tiktoken_ext.openai_public',
  ];

  // 4. 运行 PyInstaller
  console.log('\n[4/5] Running PyInstaller...');
  // 使用桌面专用入口（直接传 app 对象给 uvicorn，避免字符串 import 在 frozen 环境失败）
  const desktopEntry = join(DESKTOP_DIR, 'scripts', 'desktop-entry.py');
  const apiMainPy = desktopEntry;

  const assetsSrc = join(API_DIR, 'app', 'assets');
  const assetsExist = existsSync(assetsSrc);
  const dataSrc = join(API_DIR, 'data');
  const dataExist = existsSync(dataSrc);

  const specPath = join(BUILD_DIR, 'querygpt-api.spec');
  const outDir = join(ROOT, 'dist', 'querygpt-api');
  const distDir = join(BUILD_DIR, 'dist').replace(/\\/g, '\\\\');

  // 生成 runtime hook：强制导入 aiosqlite（hiddenimport 无法保证纯 Python 包被打包）
  const runtimeHookContent = 'import aiosqlite  # noqa: F401\n';
  const runtimeHookPath = join(BUILD_DIR, 'runtime-hook.py');
  writeFileSync(runtimeHookPath, runtimeHookContent);

  const spec = `
# -*- mode: python ; coding: utf-8 -*-
import importlib, os
from PyInstaller.utils.hooks import collect_data_files
block_cipher = None
distpath = '${distDir}'

# 收集需要数据文件的包
_extra_datas = []
for _pkg in ['tiktoken_ext', 'litellm', 'certifi', 'charset_normalizer']:
    try:
        _extra_datas += collect_data_files(_pkg)
    except Exception:
        pass

a = Analysis(
    ['${apiMainPy.replace(/\\/g, '\\\\')}'],
    pathex=['${API_DIR.replace(/\\/g, '\\\\')}'],
    binaries=[],
    datas=[
${assetsExist ? `        ('${assetsSrc.replace(/\\/g, '\\\\')}', 'app\\\\assets'),` : ''}
${dataExist ? `        ('${dataSrc.replace(/\\/g, '\\\\')}', 'data'),` : ''}
    ] + _extra_datas,
    hiddenimports=[${hiddenImports.map(s => `'${s}'`).join(', ')}],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['${runtimeHookPath.replace(/\\/g, '\\\\')}'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='querygpt-api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='querygpt-api',
)
`;

  writeFileSync(specPath, spec);

  run(`${python} -m PyInstaller -y ${specPath}`, { stdio: 'inherit' });

  // 5. 复制输出到 backend/
  console.log('\n[5/5] Copying to apps/desktop/backend/...');

  // 先在原始输出目录修复绝对符号链接（此时绝对路径仍然有效，existsSync 能正确判断目标类型）
  if (process.platform !== 'win32') {
    fixSymlinks(outDir);
  }

  if (existsSync(BACKEND_OUT)) rmSync(BACKEND_OUT, { recursive: true });

  if (process.platform === 'win32') {
    cpSync(outDir, BACKEND_OUT, { recursive: true });
  } else {
    // cp -a 保留符号链接原样，不会触发 ENOTSUP
    run(`cp -a "${outDir}/." "${BACKEND_OUT}/"`, { cwd: ROOT });
  }

  // 复制 .env.example
  const envExample = join(API_DIR, '.env.example');
  if (existsSync(envExample)) {
    copyFileSync(envExample, join(BACKEND_OUT, '.env.example'));
  }

  console.log(`\n✓ Backend built at: ${BACKEND_OUT}`);
  console.log(`  (Next step: run scripts/build-next.ts to build the frontend)`);
}

main().catch((err) => {
  console.error('Build failed:', err);
  process.exit(1);
});

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
import { existsSync, mkdirSync, writeFileSync, copyFileSync, cpSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';

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
  writeFileSync(join(BUILD_DIR, 'requirements.txt'), requirements);

  // 2. 创建 build venv（使用 Python 3.13，PyInstaller 6.19.0 需要）
  console.log('\n[2/5] Creating build venv with Python 3.13...');
  const venvDir = join(BUILD_DIR, '.build-venv');
  if (existsSync(venvDir)) rmSync(venvDir, { recursive: true });
  const pythonBin = execSync('which python3.13 || which python3', { encoding: 'utf-8' }).trim();
  run(`${pythonBin} -m venv ${venvDir}`);

  const pip = join(venvDir, process.platform === 'win32' ? 'Scripts/pip.exe' : 'bin/pip');
  const python = join(venvDir, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python3');

  // 安装 pyinstaller 和依赖
  console.log('Installing PyInstaller and dependencies...');
  run(`${pip} install pyinstaller==6.19.0`);
  run(`${pip} install -r ${join(BUILD_DIR, 'requirements.txt')}`);

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
    runtime_hooks=[],
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
  if (existsSync(BACKEND_OUT)) rmSync(BACKEND_OUT, { recursive: true });
  cpSync(outDir, BACKEND_OUT, { recursive: true });

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

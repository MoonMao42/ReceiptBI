import fs from 'node:fs';
import path from 'node:path';

export const FRONTEND_BUILD_MANIFEST_NAME = 'receiptbi-frontend-build.json';

export interface FrontendBuildManifest {
  readonly formatVersion: 1;
  readonly buildId: string;
  readonly builder: 'apps/desktop/scripts/build-next.ts';
}

function requireFile(filePath: string, label: string): void {
  if (!fs.statSync(filePath, { throwIfNoEntry: false })?.isFile()) {
    throw new Error(`${label} is missing: ${filePath}`);
  }
}

function requireDirectory(directoryPath: string, label: string): void {
  if (!fs.statSync(directoryPath, { throwIfNoEntry: false })?.isDirectory()) {
    throw new Error(`${label} is missing: ${directoryPath}`);
  }
}

export function readFrontendBuildId(bundleDirectory: string): string {
  const buildIdPath = path.join(bundleDirectory, '.next', 'BUILD_ID');
  requireFile(buildIdPath, 'Next.js BUILD_ID');
  const buildId = fs.readFileSync(buildIdPath, 'utf-8').trim();
  if (!buildId || !/^[A-Za-z0-9_-]+$/.test(buildId)) {
    throw new Error(`Next.js BUILD_ID is invalid: ${buildIdPath}`);
  }
  return buildId;
}

export function writeFrontendBuildManifest(bundleDirectory: string): FrontendBuildManifest {
  const manifest: FrontendBuildManifest = {
    formatVersion: 1,
    buildId: readFrontendBuildId(bundleDirectory),
    builder: 'apps/desktop/scripts/build-next.ts',
  };
  fs.writeFileSync(
    path.join(bundleDirectory, FRONTEND_BUILD_MANIFEST_NAME),
    `${JSON.stringify(manifest, null, 2)}\n`,
    'utf-8'
  );
  return manifest;
}

export function validateFrontendBundle(bundleDirectory: string): FrontendBuildManifest {
  requireFile(path.join(bundleDirectory, 'server.js'), 'Next.js standalone server');
  requireFile(
    path.join(bundleDirectory, '.next', 'build-manifest.json'),
    'Next.js build manifest'
  );

  const buildId = readFrontendBuildId(bundleDirectory);
  requireDirectory(
    path.join(bundleDirectory, '.next', 'static', buildId),
    'Next.js build-specific static assets'
  );

  const manifestPath = path.join(bundleDirectory, FRONTEND_BUILD_MANIFEST_NAME);
  requireFile(manifestPath, 'ReceiptBI frontend build manifest');

  let manifest: unknown;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  } catch (error) {
    throw new Error(`ReceiptBI frontend build manifest is invalid: ${manifestPath}`, {
      cause: error,
    });
  }

  if (
    !manifest ||
    typeof manifest !== 'object' ||
    (manifest as Partial<FrontendBuildManifest>).formatVersion !== 1 ||
    (manifest as Partial<FrontendBuildManifest>).builder !==
      'apps/desktop/scripts/build-next.ts' ||
    (manifest as Partial<FrontendBuildManifest>).buildId !== buildId
  ) {
    throw new Error(`ReceiptBI frontend build manifest does not match BUILD_ID: ${manifestPath}`);
  }

  return manifest as FrontendBuildManifest;
}

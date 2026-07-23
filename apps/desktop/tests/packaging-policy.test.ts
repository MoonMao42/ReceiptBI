import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  assertNoBundledRuntimeData,
  assertNoBundledSensitiveFiles,
} from '../scripts/packaging-policy.js';

function withTemporaryBundle(run: (root: string) => void): void {
  const root = mkdtempSync(path.join(os.tmpdir(), 'receiptbi-package-policy-'));
  try {
    run(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test('accepts immutable application resources', () => {
  withTemporaryBundle((root) => {
    mkdirSync(path.join(root, '_internal', 'app', 'assets'), { recursive: true });
    writeFileSync(path.join(root, '_internal', 'app', 'assets', 'prompt.txt'), 'template');
    writeFileSync(path.join(root, '.env.example'), 'OPENAI_API_KEY=');

    assert.doesNotThrow(() => assertNoBundledRuntimeData(root));
  });
});

test('rejects project workspaces and local databases', () => {
  withTemporaryBundle((root) => {
    mkdirSync(path.join(root, '_internal', 'Data'), { recursive: true });
    writeFileSync(path.join(root, '_internal', 'Data', 'orders.csv'), 'private');

    assert.throws(
      () => assertNoBundledRuntimeData(root),
      /runtime-only data: .*_internal.*Data/
    );
  });
});

test('rejects credentials and per-project dependency environments anywhere', () => {
  withTemporaryBundle((root) => {
    mkdirSync(path.join(root, 'nested', '.python'), { recursive: true });
    writeFileSync(path.join(root, '.ENV.production'), 'OPENAI_API_KEY=secret');
    writeFileSync(path.join(root, 'workspace.sqlite-journal'), 'private');
    writeFileSync(path.join(root, 'warehouse.duckdb.wal'), 'private');
    writeFileSync(path.join(root, 'warehouse.ddb'), 'private');

    assert.throws(() => assertNoBundledRuntimeData(root), (error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      return (
        message.includes('.ENV.production')
        && message.includes('.python')
        && message.includes('workspace.sqlite-journal')
        && message.includes('warehouse.duckdb.wal')
        && message.includes('warehouse.ddb')
      );
    });
  });
});

test('allows product route directories while rejecting sensitive files in all resources', () => {
  withTemporaryBundle((root) => {
    mkdirSync(path.join(root, 'next', 'server', 'app', 'projects'), { recursive: true });
    writeFileSync(path.join(root, 'next', 'server', 'app', 'projects', 'page.js'), 'route');

    assert.doesNotThrow(() => assertNoBundledSensitiveFiles(root));
    writeFileSync(path.join(root, 'next', '.env.local'), 'OPENAI_API_KEY=secret');
    assert.throws(
      () => assertNoBundledSensitiveFiles(root),
      /runtime-only data: .*\.env\.local/
    );
  });
});

test(
  'rejects links that escape the immutable bundle',
  { skip: process.platform === 'win32' },
  () => {
    withTemporaryBundle((root) => {
      symlinkSync(path.join(os.tmpdir(), 'receiptbi-external-resource'), path.join(root, 'resource'));
      assert.throws(
        () => assertNoBundledRuntimeData(root),
        /runtime-only data: resource/
      );
    });
  }
);

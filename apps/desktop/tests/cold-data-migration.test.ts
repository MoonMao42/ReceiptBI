import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  ColdMigrationError,
  executeColdMigration,
  inspectColdMigration,
} from '../electron/cold-data-migration.js';
import { prepareDesktopDataPaths } from '../electron/data-migration.js';

function fixture(): string {
  return mkdtempSync(path.join(os.tmpdir(), 'receiptbi-cold-migration-'));
}

function legacyDatabase(homeDir: string, root = '.querygpt-desktop'): string {
  const dataDir = path.join(homeDir, root, 'data');
  mkdirSync(dataDir, { recursive: true });
  const database = path.join(dataDir, 'querygpt.db');
  writeFileSync(database, 'legacy-sqlite-bytes');
  return database;
}

test('inspection is read-only when no historical data exists', () => {
  const homeDir = fixture();
  try {
    const plan = inspectColdMigration(homeDir);
    assert.equal(plan.kind, 'none');
    assert.equal(existsSync(path.join(homeDir, '.receiptbi-desktop')), false);
  } finally {
    rmSync(homeDir, { recursive: true, force: true });
  }
});

test('cold migration copies a legacy root, renames SQLite files, and preserves source and backup', async () => {
  const homeDir = fixture();
  try {
    const sourceDatabase = legacyDatabase(homeDir);
    writeFileSync(`${sourceDatabase}-wal`, 'committed-wal-bytes');
    writeFileSync(`${sourceDatabase}-shm`, 'shared-memory-bytes');
    writeFileSync(path.join(homeDir, '.querygpt-desktop', 'preferences.json'), '{"theme":"dawn"}');

    const receipt = executeColdMigration(homeDir, {
      legacyAppClosed: true,
      migrationId: 'migration-root-001',
      now: new Date('2026-07-19T04:00:00.000Z'),
    });

    assert.ok(receipt);
    assert.equal(receipt.kind, 'legacy-root');
    assert.deepEqual(receipt.sqliteSidecars, ['-wal', '-shm']);
    assert.equal(readFileSync(sourceDatabase, 'utf8'), 'legacy-sqlite-bytes');
    assert.equal(
      readFileSync(path.join(homeDir, '.receiptbi-desktop', 'data', 'receiptbi.db'), 'utf8'),
      'legacy-sqlite-bytes'
    );
    assert.equal(
      readFileSync(path.join(homeDir, '.receiptbi-desktop', 'data', 'receiptbi.db-wal'), 'utf8'),
      'committed-wal-bytes'
    );
    assert.equal(
      existsSync(path.join(homeDir, '.receiptbi-desktop', 'data', 'querygpt.db')),
      false
    );
    assert.equal(
      readFileSync(
        path.join(homeDir, '.receiptbi-migration-backups', 'migration-root-001', 'querygpt.db'),
        'utf8'
      ),
      'legacy-sqlite-bytes'
    );
    assert.equal(
      readFileSync(path.join(homeDir, '.receiptbi-desktop', 'preferences.json'), 'utf8'),
      '{"theme":"dawn"}'
    );

    const paths = await prepareDesktopDataPaths(homeDir);
    assert.equal(paths.databasePath, path.join(homeDir, '.receiptbi-desktop', 'data', 'receiptbi.db'));
  } finally {
    rmSync(homeDir, { recursive: true, force: true });
  }
});

test('cold migration renames a legacy database already inside the ReceiptBI root', () => {
  const homeDir = fixture();
  try {
    const sourceDatabase = legacyDatabase(homeDir, '.receiptbi-desktop');
    const receipt = executeColdMigration(homeDir, {
      legacyAppClosed: true,
      migrationId: 'migration-database-001',
    });

    assert.ok(receipt);
    assert.equal(receipt.kind, 'legacy-database');
    assert.equal(readFileSync(sourceDatabase, 'utf8'), 'legacy-sqlite-bytes');
    assert.equal(
      readFileSync(path.join(homeDir, '.receiptbi-desktop', 'data', 'receiptbi.db'), 'utf8'),
      'legacy-sqlite-bytes'
    );
  } finally {
    rmSync(homeDir, { recursive: true, force: true });
  }
});

test('execution requires an explicit acknowledgement that QueryGPT is closed', () => {
  const homeDir = fixture();
  try {
    legacyDatabase(homeDir);
    assert.throws(
      () => executeColdMigration(homeDir, { legacyAppClosed: false }),
      (error: unknown) =>
        error instanceof ColdMigrationError && /Close QueryGPT/.test(error.message)
    );
    assert.equal(existsSync(path.join(homeDir, '.receiptbi-desktop')), false);
  } finally {
    rmSync(homeDir, { recursive: true, force: true });
  }
});

test('ambiguous coexisting roots fail closed without merging data', () => {
  const homeDir = fixture();
  try {
    legacyDatabase(homeDir);
    mkdirSync(path.join(homeDir, '.receiptbi-desktop'), { recursive: true });
    assert.throws(
      () => inspectColdMigration(homeDir),
      (error: unknown) =>
        error instanceof ColdMigrationError && /Refusing to merge/.test(error.message)
    );
    assert.equal(
      existsSync(path.join(homeDir, '.receiptbi-desktop', 'data', 'receiptbi.db')),
      false
    );
  } finally {
    rmSync(homeDir, { recursive: true, force: true });
  }
});

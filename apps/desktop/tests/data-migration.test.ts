import assert from 'node:assert/strict';
import {
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  LEGACY_DATA_DIRECTORY,
  LEGACY_DATABASE_NAME,
  LegacyDataMigrationRequiredError,
  RECEIPTBI_DATA_DIRECTORY,
  RECEIPTBI_DATABASE_NAME,
  prepareDesktopDataPaths,
} from '../electron/data-migration.js';

function temporaryHome(): { homeDir: string; cleanup: () => void } {
  const homeDir = mkdtempSync(path.join(os.tmpdir(), 'receiptbi-desktop-migration-'));
  return {
    homeDir,
    cleanup: () => rmSync(homeDir, { recursive: true, force: true }),
  };
}

type TreeSnapshot = Readonly<Record<string, string>>;

function snapshotTree(root: string): TreeSnapshot | null {
  if (!existsSync(root)) return null;
  const snapshot: Record<string, string> = {};

  const visit = (candidate: string, relative: string): void => {
    const stats = lstatSync(candidate);
    const key = relative || '.';
    if (stats.isDirectory()) {
      snapshot[key] = `directory:${stats.mode & 0o777}`;
      for (const name of readdirSync(candidate).sort()) {
        visit(path.join(candidate, name), relative ? path.join(relative, name) : name);
      }
      return;
    }
    if (stats.isSymbolicLink()) {
      snapshot[key] = `symlink:${readlinkSync(candidate)}`;
      return;
    }
    snapshot[key] = `file:${stats.mode & 0o777}:${readFileSync(candidate).toString('base64')}`;
  };

  visit(root, '');
  return snapshot;
}

function assertColdMigrationError(error: unknown): boolean {
  assert.ok(error instanceof LegacyDataMigrationRequiredError);
  assert.match(error.message, /close the legacy application/i);
  assert.match(error.message, /verified backup/i);
  assert.match(error.message, /cold migration/i);
  return true;
}

test('a fresh install creates only the ReceiptBI data directory', async () => {
  const fixture = temporaryHome();
  try {
    const result = await prepareDesktopDataPaths(fixture.homeDir);

    assert.equal(result.migrationKind, 'new');
    assert.equal(result.userDataDir, path.join(fixture.homeDir, RECEIPTBI_DATA_DIRECTORY));
    assert.equal(result.databasePath, path.join(result.dataDir, RECEIPTBI_DATABASE_NAME));
    assert.equal(existsSync(result.userDataDir), true);
    assert.equal(existsSync(result.dataDir), true);
    assert.equal(existsSync(result.databasePath), false);
    assert.equal(existsSync(path.join(fixture.homeDir, LEGACY_DATA_DIRECTORY)), false);
  } finally {
    fixture.cleanup();
  }
});

test('an existing ReceiptBI directory and database remain current and unchanged', async () => {
  const fixture = temporaryHome();
  try {
    const currentDir = path.join(fixture.homeDir, RECEIPTBI_DATA_DIRECTORY);
    const currentDatabase = path.join(currentDir, 'data', RECEIPTBI_DATABASE_NAME);
    mkdirSync(path.dirname(currentDatabase), { recursive: true });
    writeFileSync(path.join(currentDir, 'project-state.json'), '{"kept":true}\n');
    writeFileSync(currentDatabase, 'current sqlite bytes');
    const before = snapshotTree(currentDir);

    const result = await prepareDesktopDataPaths(fixture.homeDir);

    assert.equal(result.migrationKind, 'current');
    assert.equal(result.userDataDir, currentDir);
    assert.equal(result.databasePath, currentDatabase);
    assert.deepEqual(snapshotTree(currentDir), before);
    assert.equal(existsSync(path.join(fixture.homeDir, LEGACY_DATA_DIRECTORY)), false);
  } finally {
    fixture.cleanup();
  }
});

test('a legacy-only root requires an explicit cold migration with every byte untouched', async () => {
  const fixture = temporaryHome();
  try {
    const legacyDir = path.join(fixture.homeDir, LEGACY_DATA_DIRECTORY);
    const currentDir = path.join(fixture.homeDir, RECEIPTBI_DATA_DIRECTORY);
    const legacyDatabase = path.join(legacyDir, 'data', LEGACY_DATABASE_NAME);
    mkdirSync(path.dirname(legacyDatabase), { recursive: true });
    writeFileSync(path.join(legacyDir, '.env'), 'ENCRYPTION_KEY=legacy-secret\n');
    writeFileSync(path.join(legacyDir, 'project-state.json'), '{"kept":true}\n');
    writeFileSync(legacyDatabase, 'legacy sqlite bytes');
    writeFileSync(`${legacyDatabase}-wal`, 'live WAL bytes');
    writeFileSync(`${legacyDatabase}-shm`, 'live SHM bytes');
    writeFileSync(`${legacyDatabase}-journal`, 'live journal bytes');
    const before = snapshotTree(legacyDir);

    await assert.rejects(
      () => prepareDesktopDataPaths(fixture.homeDir),
      assertColdMigrationError
    );

    assert.deepEqual(snapshotTree(legacyDir), before);
    assert.equal(existsSync(currentDir), false);
  } finally {
    fixture.cleanup();
  }
});

test('coexisting roots use ReceiptBI without merging or changing either tree', async () => {
  const fixture = temporaryHome();
  try {
    const currentDir = path.join(fixture.homeDir, RECEIPTBI_DATA_DIRECTORY);
    const legacyDir = path.join(fixture.homeDir, LEGACY_DATA_DIRECTORY);
    const currentDatabase = path.join(currentDir, 'data', RECEIPTBI_DATABASE_NAME);
    const legacyDatabase = path.join(legacyDir, 'data', LEGACY_DATABASE_NAME);
    mkdirSync(path.dirname(currentDatabase), { recursive: true });
    mkdirSync(path.dirname(legacyDatabase), { recursive: true });
    writeFileSync(path.join(currentDir, 'owner.txt'), 'current');
    writeFileSync(path.join(legacyDir, 'owner.txt'), 'legacy');
    writeFileSync(currentDatabase, 'current database');
    writeFileSync(legacyDatabase, 'legacy database');
    writeFileSync(`${legacyDatabase}-wal`, 'legacy WAL');
    const currentBefore = snapshotTree(currentDir);
    const legacyBefore = snapshotTree(legacyDir);

    const result = await prepareDesktopDataPaths(fixture.homeDir);

    assert.equal(result.migrationKind, 'coexisting');
    assert.equal(result.userDataDir, currentDir);
    assert.equal(result.databasePath, currentDatabase);
    assert.deepEqual(snapshotTree(currentDir), currentBefore);
    assert.deepEqual(snapshotTree(legacyDir), legacyBefore);
    assert.ok(result.events.some((event) => event.includes('without changing either')));
  } finally {
    fixture.cleanup();
  }
});

test('querygpt.db inside the current root fails closed without creating receiptbi.db', async () => {
  const fixture = temporaryHome();
  try {
    const currentDir = path.join(fixture.homeDir, RECEIPTBI_DATA_DIRECTORY);
    const legacyDir = path.join(fixture.homeDir, LEGACY_DATA_DIRECTORY);
    const legacyDatabase = path.join(currentDir, 'data', LEGACY_DATABASE_NAME);
    const currentDatabase = path.join(currentDir, 'data', RECEIPTBI_DATABASE_NAME);
    mkdirSync(path.dirname(legacyDatabase), { recursive: true });
    writeFileSync(path.join(currentDir, 'owner.txt'), 'current root');
    writeFileSync(legacyDatabase, 'legacy database');
    writeFileSync(`${legacyDatabase}-wal`, 'live WAL');
    writeFileSync(`${legacyDatabase}-shm`, 'live SHM');
    writeFileSync(`${legacyDatabase}-journal`, 'live journal');
    const before = snapshotTree(currentDir);

    await assert.rejects(
      () => prepareDesktopDataPaths(fixture.homeDir),
      assertColdMigrationError
    );

    assert.deepEqual(snapshotTree(currentDir), before);
    assert.equal(existsSync(currentDatabase), false);
    assert.equal(existsSync(legacyDir), false);
  } finally {
    fixture.cleanup();
  }
});

test('receiptbi.db wins when both database names exist and neither is changed', async () => {
  const fixture = temporaryHome();
  try {
    const currentDir = path.join(fixture.homeDir, RECEIPTBI_DATA_DIRECTORY);
    const dataDir = path.join(currentDir, 'data');
    const legacyDatabase = path.join(dataDir, LEGACY_DATABASE_NAME);
    const currentDatabase = path.join(dataDir, RECEIPTBI_DATABASE_NAME);
    mkdirSync(dataDir, { recursive: true });
    writeFileSync(legacyDatabase, 'legacy');
    writeFileSync(`${legacyDatabase}-wal`, 'legacy WAL');
    writeFileSync(currentDatabase, 'current');
    const before = snapshotTree(currentDir);

    const result = await prepareDesktopDataPaths(fixture.homeDir);

    assert.equal(result.migrationKind, 'current');
    assert.equal(result.databasePath, currentDatabase);
    assert.deepEqual(snapshotTree(currentDir), before);
    assert.ok(result.events.some((event) => event.includes('without changing querygpt.db')));
  } finally {
    fixture.cleanup();
  }
});

test('coexisting roots still fail closed when the current root has only querygpt.db', async () => {
  const fixture = temporaryHome();
  try {
    const currentDir = path.join(fixture.homeDir, RECEIPTBI_DATA_DIRECTORY);
    const legacyDir = path.join(fixture.homeDir, LEGACY_DATA_DIRECTORY);
    const currentLegacyDatabase = path.join(currentDir, 'data', LEGACY_DATABASE_NAME);
    mkdirSync(path.dirname(currentLegacyDatabase), { recursive: true });
    mkdirSync(legacyDir);
    writeFileSync(currentLegacyDatabase, 'current-root legacy database');
    writeFileSync(path.join(legacyDir, 'owner.txt'), 'legacy root');
    const currentBefore = snapshotTree(currentDir);
    const legacyBefore = snapshotTree(legacyDir);

    await assert.rejects(
      () => prepareDesktopDataPaths(fixture.homeDir),
      assertColdMigrationError
    );

    assert.deepEqual(snapshotTree(currentDir), currentBefore);
    assert.deepEqual(snapshotTree(legacyDir), legacyBefore);
    assert.equal(
      existsSync(path.join(currentDir, 'data', RECEIPTBI_DATABASE_NAME)),
      false
    );
  } finally {
    fixture.cleanup();
  }
});

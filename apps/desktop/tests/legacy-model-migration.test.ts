import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
  chmodSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  LEGACY_MODEL_DATABASE_RELATIVE_PATH,
  LEGACY_MODEL_MIGRATION_BACKUP_RELATIVE_DIRECTORY,
  LegacyModelMigrationError,
  markLegacyModelMigrationImported,
  prepareLegacyModelMigration,
  validateLegacyModelMigrationAck,
  type LegacyModelMigrationPreparation,
} from '../electron/legacy-model-migration.js';

const LEGACY_KEY = Buffer.alloc(32, 0x6c)
  .toString('base64')
  .replace(/\+/g, '-')
  .replace(/\//g, '_');

interface Fixture {
  readonly root: string;
  readonly userDataDir: string;
  readonly legacyDatabase: string;
  readonly environment: string;
  readonly cleanup: () => void;
}

interface FileSnapshot {
  readonly bytes: Buffer;
  readonly sha256: string;
}

function temporaryFixture(): Fixture {
  const root = mkdtempSync(path.join(os.tmpdir(), 'receiptbi-legacy-model-'));
  const userDataDir = path.join(root, 'prepared-user-data');
  mkdirSync(userDataDir, { mode: 0o700 });
  return {
    root,
    userDataDir,
    legacyDatabase: path.join(userDataDir, LEGACY_MODEL_DATABASE_RELATIVE_PATH),
    environment: path.join(userDataDir, '.env'),
    cleanup: () => rmSync(root, { recursive: true, force: true }),
  };
}

function createLegacySource(
  fixture: Fixture,
  options: {
    readonly companions?: readonly ('-wal' | '-shm' | '-journal')[];
    readonly environment?: string;
  } = {}
): void {
  mkdirSync(path.dirname(fixture.legacyDatabase), { recursive: true });
  writeFileSync(fixture.legacyDatabase, 'live legacy database', { mode: 0o644 });
  for (const suffix of options.companions ?? []) {
    writeFileSync(`${fixture.legacyDatabase}${suffix}`, `live ${suffix}`, {
      mode: 0o644,
    });
  }
  if (options.environment !== undefined) {
    writeFileSync(fixture.environment, options.environment, { mode: 0o600 });
  }
}

function assertReady(
  preparation: LegacyModelMigrationPreparation
): asserts preparation is Extract<LegacyModelMigrationPreparation, { status: 'ready' }> {
  assert.equal(preparation.status, 'ready');
}

function stateFile(fixture: Fixture): string {
  return path.join(
    fixture.userDataDir,
    LEGACY_MODEL_MIGRATION_BACKUP_RELATIVE_DIRECTORY,
    'state.json'
  );
}

function mode(candidate: string): number {
  return lstatSync(candidate).mode & 0o777;
}

function snapshotFiles(candidates: readonly string[]): ReadonlyMap<string, FileSnapshot> {
  return new Map(
    candidates.map((candidate) => {
      const bytes = readFileSync(candidate);
      return [
        candidate,
        { bytes, sha256: createHash('sha256').update(bytes).digest('hex') },
      ] as const;
    })
  );
}

function assertFilesUnchanged(before: ReadonlyMap<string, FileSnapshot>): void {
  for (const [candidate, expected] of before) {
    const bytes = readFileSync(candidate);
    assert.deepEqual(bytes, expected.bytes);
    assert.equal(createHash('sha256').update(bytes).digest('hex'), expected.sha256);
  }
}

function publishBackendSnapshot(preparation: Extract<
  LegacyModelMigrationPreparation,
  { status: 'ready' }
>): void {
  const temporary = path.join(
    path.dirname(preparation.databaseSnapshotPath),
    '.backend-snapshot.tmp'
  );
  writeFileSync(temporary, 'sqlite backup api output', { mode: 0o600 });
  renameSync(temporary, preparation.databaseSnapshotPath);
  if (process.platform !== 'win32') {
    chmodSync(preparation.databaseSnapshotPath, 0o600);
  }
}

test('migration ACK requires a committed status bound to this launch', () => {
  for (const status of ['imported', 'already_present', 'empty'] as const) {
    assert.equal(
      validateLegacyModelMigrationAck(
        { status, instance_token: 'current-launch' },
        'current-launch'
      ),
      status
    );
  }
  for (const invalid of [
    null,
    { status: 'imported' },
    { status: 'imported', instance_token: 'stale-launch' },
    { status: 'failed', instance_token: 'current-launch' },
  ]) {
    assert.throws(
      () => validateLegacyModelMigrationAck(invalid, 'current-launch'),
      LegacyModelMigrationError
    );
  }
});

test('no legacy database returns absent without inspecting or parsing .env', () => {
  const fixture = temporaryFixture();
  try {
    const outside = path.join(fixture.root, 'outside.env');
    writeFileSync(outside, `ENCRYPTION_KEY=${LEGACY_KEY}\n`);
    symlinkSync(outside, fixture.environment);

    assert.deepEqual(prepareLegacyModelMigration(fixture.userDataDir), {
      status: 'absent',
    });
    assert.equal(
      existsSync(
        path.join(
          fixture.userDataDir,
          LEGACY_MODEL_MIGRATION_BACKUP_RELATIVE_DIRECTORY
        )
      ),
      false
    );
  } finally {
    fixture.cleanup();
  }
});

test('preparation reserves a private empty target and never touches live SQLite files', () => {
  const fixture = temporaryFixture();
  try {
    const originalEnvironment = [
      '# legacy environment',
      `export ENCRYPTION_KEY="${LEGACY_KEY}"`,
      'UNRELATED=value',
      '',
    ].join('\n');
    createLegacySource(fixture, {
      companions: ['-wal', '-shm', '-journal'],
      environment: originalEnvironment,
    });
    const activePaths = [
      fixture.legacyDatabase,
      `${fixture.legacyDatabase}-wal`,
      `${fixture.legacyDatabase}-shm`,
      `${fixture.legacyDatabase}-journal`,
      fixture.environment,
    ];
    const before = snapshotFiles(activePaths);

    const first = prepareLegacyModelMigration(fixture.userDataDir);
    assertReady(first);
    assert.equal(first.databaseSourcePath, fixture.legacyDatabase);
    assert.equal(path.basename(first.databaseSnapshotPath), 'model-config.sqlite3');
    assert.equal(existsSync(first.databaseSnapshotPath), false);
    assert.equal(first.legacyEncryptionKey, LEGACY_KEY);

    const archiveDirectory = path.dirname(first.databaseSnapshotPath);
    assert.deepEqual(readdirSync(archiveDirectory), ['environment.backup']);
    assert.equal(
      readFileSync(path.join(archiveDirectory, 'environment.backup'), 'utf-8'),
      originalEnvironment
    );
    if (process.platform !== 'win32') {
      assert.equal(mode(archiveDirectory), 0o700);
      assert.equal(mode(path.join(archiveDirectory, 'environment.backup')), 0o600);
      assert.equal(mode(stateFile(fixture)), 0o600);
    }

    const repeated = prepareLegacyModelMigration(fixture.userDataDir);
    assertReady(repeated);
    assert.equal(repeated.migrationId, first.migrationId);
    assert.equal(repeated.databaseSourcePath, fixture.legacyDatabase);
    assert.equal(repeated.databaseSnapshotPath, first.databaseSnapshotPath);
    assert.equal(existsSync(repeated.databaseSnapshotPath), false);
    assertFilesUnchanged(before);

    const markerText = readFileSync(stateFile(fixture), 'utf-8');
    const marker = JSON.parse(markerText) as Record<string, unknown>;
    assert.deepEqual(Object.keys(marker).sort(), [
      'environmentBackup',
      'migrationId',
      'status',
      'version',
    ]);
    assert.equal(markerText.includes(LEGACY_KEY), false);
    assert.equal(markerText.includes(fixture.userDataDir), false);
    assert.equal(markerText.includes(fixture.legacyDatabase), false);
    assert.equal(markerText.includes(first.databaseSnapshotPath), false);
    assert.equal(markerText.includes('querygpt-ts.db'), false);
    assert.equal(markerText.includes('model-config.sqlite3'), false);
    assert.equal(markerText.includes('assets'), false);
  } finally {
    fixture.cleanup();
  }
});

test('a source without a legacy key returns ready with an explicit null key', () => {
  const fixture = temporaryFixture();
  try {
    createLegacySource(fixture);
    const preparation = prepareLegacyModelMigration(fixture.userDataDir);
    assertReady(preparation);
    assert.equal(preparation.databaseSourcePath, fixture.legacyDatabase);
    assert.equal(preparation.legacyEncryptionKey, null);
    assert.equal(existsSync(preparation.databaseSnapshotPath), false);
  } finally {
    fixture.cleanup();
  }
});

test('active source and environment path escapes are rejected while companions are ignored', async (t) => {
  await t.test('database symlink', () => {
    const fixture = temporaryFixture();
    try {
      const outside = path.join(fixture.root, 'outside.db');
      mkdirSync(path.dirname(fixture.legacyDatabase), { recursive: true });
      writeFileSync(outside, 'outside database');
      symlinkSync(outside, fixture.legacyDatabase);

      assert.throws(
        () => prepareLegacyModelMigration(fixture.userDataDir),
        LegacyModelMigrationError
      );
      assert.equal(readFileSync(outside, 'utf-8'), 'outside database');
    } finally {
      fixture.cleanup();
    }
  });

  await t.test('data directory escape', () => {
    const fixture = temporaryFixture();
    try {
      const outsideData = path.join(fixture.root, 'outside-data');
      mkdirSync(outsideData);
      writeFileSync(path.join(outsideData, 'querygpt-ts.db'), 'outside database');
      symlinkSync(outsideData, path.join(fixture.userDataDir, 'data'));

      assert.throws(
        () => prepareLegacyModelMigration(fixture.userDataDir),
        LegacyModelMigrationError
      );
      assert.equal(
        readFileSync(path.join(outsideData, 'querygpt-ts.db'), 'utf-8'),
        'outside database'
      );
    } finally {
      fixture.cleanup();
    }
  });

  await t.test('environment symlink', () => {
    const fixture = temporaryFixture();
    try {
      createLegacySource(fixture);
      const outside = path.join(fixture.root, 'outside.env');
      writeFileSync(outside, `ENCRYPTION_KEY=${LEGACY_KEY}\n`);
      symlinkSync(outside, fixture.environment);

      assert.throws(
        () => prepareLegacyModelMigration(fixture.userDataDir),
        LegacyModelMigrationError
      );
      assert.equal(readFileSync(outside, 'utf-8'), `ENCRYPTION_KEY=${LEGACY_KEY}\n`);
    } finally {
      fixture.cleanup();
    }
  });

  await t.test('SQLite companion symlinks are not inspected or touched', () => {
    const fixture = temporaryFixture();
    try {
      createLegacySource(fixture, { environment: `ENCRYPTION_KEY=${LEGACY_KEY}\n` });
      const outside = path.join(fixture.root, 'outside-wal');
      writeFileSync(outside, 'live outside WAL');
      symlinkSync(outside, `${fixture.legacyDatabase}-wal`);

      const preparation = prepareLegacyModelMigration(fixture.userDataDir);
      assertReady(preparation);
      assert.equal(existsSync(preparation.databaseSnapshotPath), false);
      assert.equal(readFileSync(outside, 'utf-8'), 'live outside WAL');
      assert.equal(lstatSync(`${fixture.legacyDatabase}-wal`).isSymbolicLink(), true);
    } finally {
      fixture.cleanup();
    }
  });
});

test('a backend snapshot survives source disappearance and imported marking is idempotent', () => {
  const fixture = temporaryFixture();
  try {
    const originalEnvironment = `ENCRYPTION_KEY=${LEGACY_KEY}\n`;
    createLegacySource(fixture, {
      companions: ['-wal', '-shm', '-journal'],
      environment: originalEnvironment,
    });
    const preparation = prepareLegacyModelMigration(fixture.userDataDir);
    assertReady(preparation);
    assert.equal(existsSync(preparation.databaseSnapshotPath), false);

    publishBackendSnapshot(preparation);
    const snapshotBefore = readFileSync(preparation.databaseSnapshotPath);
    for (const suffix of ['', '-wal', '-shm', '-journal']) {
      rmSync(`${fixture.legacyDatabase}${suffix}`, { force: true });
    }

    const retry = prepareLegacyModelMigration(fixture.userDataDir);
    assertReady(retry);
    assert.equal(retry.databaseSourcePath, null);
    assert.equal(retry.databaseSnapshotPath, preparation.databaseSnapshotPath);
    assert.equal(retry.legacyEncryptionKey, LEGACY_KEY);

    assert.deepEqual(
      markLegacyModelMigrationImported(fixture.userDataDir, preparation.migrationId),
      { status: 'imported', migrationId: preparation.migrationId }
    );
    assert.deepEqual(
      markLegacyModelMigrationImported(fixture.userDataDir, preparation.migrationId),
      { status: 'imported', migrationId: preparation.migrationId }
    );
    assert.deepEqual(prepareLegacyModelMigration(fixture.userDataDir), {
      status: 'imported',
      migrationId: preparation.migrationId,
    });
    assert.deepEqual(readFileSync(preparation.databaseSnapshotPath), snapshotBefore);
    assert.equal(readFileSync(fixture.environment, 'utf-8'), originalEnvironment);
  } finally {
    fixture.cleanup();
  }
});

test('prepared and imported states fail closed when their required source is missing', async (t) => {
  await t.test('prepared state without source or snapshot', () => {
    const fixture = temporaryFixture();
    try {
      createLegacySource(fixture);
      const preparation = prepareLegacyModelMigration(fixture.userDataDir);
      assertReady(preparation);
      rmSync(fixture.legacyDatabase);

      assert.throws(
        () => prepareLegacyModelMigration(fixture.userDataDir),
        /Neither the legacy model source nor its backend snapshot is available/
      );
      assert.throws(
        () =>
          markLegacyModelMigrationImported(
            fixture.userDataDir,
            preparation.migrationId
          ),
        /snapshot is missing/
      );
    } finally {
      fixture.cleanup();
    }
  });

  await t.test('imported state without snapshot', () => {
    const fixture = temporaryFixture();
    try {
      createLegacySource(fixture);
      const preparation = prepareLegacyModelMigration(fixture.userDataDir);
      assertReady(preparation);
      publishBackendSnapshot(preparation);
      markLegacyModelMigrationImported(fixture.userDataDir, preparation.migrationId);
      rmSync(preparation.databaseSnapshotPath);

      assert.throws(
        () => prepareLegacyModelMigration(fixture.userDataDir),
        /imported legacy model snapshot is missing/
      );
      assert.throws(
        () =>
          markLegacyModelMigrationImported(
            fixture.userDataDir,
            preparation.migrationId
          ),
        /snapshot is missing/
      );
    } finally {
      fixture.cleanup();
    }
  });
});

test('backend snapshot path, type, and permissions are fail-closed', async (t) => {
  await t.test('snapshot symlink', () => {
    const fixture = temporaryFixture();
    try {
      createLegacySource(fixture);
      const preparation = prepareLegacyModelMigration(fixture.userDataDir);
      assertReady(preparation);
      const outside = path.join(fixture.root, 'outside-snapshot.db');
      writeFileSync(outside, 'outside snapshot', { mode: 0o600 });
      symlinkSync(outside, preparation.databaseSnapshotPath);

      assert.throws(
        () => prepareLegacyModelMigration(fixture.userDataDir),
        LegacyModelMigrationError
      );
      assert.throws(
        () =>
          markLegacyModelMigrationImported(
            fixture.userDataDir,
            preparation.migrationId
          ),
        LegacyModelMigrationError
      );
      assert.equal(readFileSync(outside, 'utf-8'), 'outside snapshot');
    } finally {
      fixture.cleanup();
    }
  });

  await t.test('snapshot directory', () => {
    const fixture = temporaryFixture();
    try {
      createLegacySource(fixture);
      const preparation = prepareLegacyModelMigration(fixture.userDataDir);
      assertReady(preparation);
      mkdirSync(preparation.databaseSnapshotPath);
      assert.throws(
        () => prepareLegacyModelMigration(fixture.userDataDir),
        LegacyModelMigrationError
      );
    } finally {
      fixture.cleanup();
    }
  });

  await t.test('public snapshot permissions', (subtest) => {
    if (process.platform === 'win32') {
      subtest.skip('POSIX permission bits are unavailable');
      return;
    }
    const fixture = temporaryFixture();
    try {
      createLegacySource(fixture);
      const preparation = prepareLegacyModelMigration(fixture.userDataDir);
      assertReady(preparation);
      writeFileSync(preparation.databaseSnapshotPath, 'public snapshot', {
        mode: 0o644,
      });
      chmodSync(preparation.databaseSnapshotPath, 0o644);

      assert.throws(
        () => prepareLegacyModelMigration(fixture.userDataDir),
        /snapshot is not private/
      );
      assert.throws(
        () =>
          markLegacyModelMigrationImported(
            fixture.userDataDir,
            preparation.migrationId
          ),
        /snapshot is not private/
      );
    } finally {
      fixture.cleanup();
    }
  });

  await t.test('public archive directory permissions', (subtest) => {
    if (process.platform === 'win32') {
      subtest.skip('POSIX permission bits are unavailable');
      return;
    }
    const fixture = temporaryFixture();
    try {
      createLegacySource(fixture);
      const preparation = prepareLegacyModelMigration(fixture.userDataDir);
      assertReady(preparation);
      chmodSync(path.dirname(preparation.databaseSnapshotPath), 0o755);

      assert.throws(
        () => prepareLegacyModelMigration(fixture.userDataDir),
        /archive is not private/
      );
    } finally {
      fixture.cleanup();
    }
  });
});

test('environment backup tampering is rejected without exposing filesystem details', () => {
  const fixture = temporaryFixture();
  try {
    createLegacySource(fixture, { environment: `ENCRYPTION_KEY=${LEGACY_KEY}\n` });
    const preparation = prepareLegacyModelMigration(fixture.userDataDir);
    assertReady(preparation);
    const backup = path.join(
      path.dirname(preparation.databaseSnapshotPath),
      'environment.backup'
    );
    writeFileSync(backup, 'tampered', { mode: 0o600 });

    assert.throws(
      () => prepareLegacyModelMigration(fixture.userDataDir),
      (error: unknown) => {
        assert.ok(error instanceof LegacyModelMigrationError);
        assert.equal(String(error).includes(fixture.root), false);
        return true;
      }
    );
    assert.equal(readFileSync(fixture.legacyDatabase, 'utf-8'), 'live legacy database');
  } finally {
    fixture.cleanup();
  }
});

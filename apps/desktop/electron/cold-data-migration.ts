import { createHash, randomUUID } from 'node:crypto';
import {
  constants as fsConstants,
  closeSync,
  copyFileSync,
  existsSync,
  lstatSync,
  mkdirSync,
  openSync,
  readSync,
  readdirSync,
  renameSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import path from 'node:path';
import {
  LEGACY_DATA_DIRECTORY,
  LEGACY_DATABASE_NAME,
  RECEIPTBI_DATA_DIRECTORY,
  RECEIPTBI_DATABASE_NAME,
} from './data-migration.js';

const BACKUP_DIRECTORY = '.receiptbi-migration-backups';
const RECEIPT_FILE = 'receiptbi-cold-migration.json';
const MAX_FILE_COUNT = 100_000;

export type ColdMigrationKind = 'legacy-root' | 'legacy-database' | 'none';

export interface ColdMigrationPlan {
  readonly kind: ColdMigrationKind;
  readonly sourceRoot: string | null;
  readonly destinationRoot: string;
  readonly sourceDatabase: string | null;
  readonly destinationDatabase: string;
  readonly reason: string;
}

export interface ColdMigrationReceipt {
  readonly version: 1;
  readonly migrationId: string;
  readonly kind: Exclude<ColdMigrationKind, 'none'>;
  readonly createdAt: string;
  readonly sourceRoot: string;
  readonly destinationRoot: string;
  readonly sourceDatabase: string;
  readonly destinationDatabase: string;
  readonly backupDatabase: string;
  readonly databaseBytes: number;
  readonly databaseSha256: string;
  readonly sqliteSidecars: readonly string[];
  readonly sourcePreserved: true;
  readonly backupPreserved: true;
}

export interface ColdMigrationOptions {
  readonly legacyAppClosed: boolean;
  readonly migrationId?: string;
  readonly now?: Date;
}

export class ColdMigrationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ColdMigrationError';
  }
}

function fail(message: string): never {
  throw new ColdMigrationError(message);
}

function assertDirectChild(homeDir: string, candidate: string): void {
  const home = path.resolve(homeDir);
  const resolved = path.resolve(candidate);
  if (path.dirname(resolved) !== home) {
    fail('The migration target is outside the selected home directory.');
  }
}

function assertOrdinaryDirectory(candidate: string, label: string): void {
  const stat = lstatSync(candidate);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    fail(`${label} must be a regular directory, not a link or special file.`);
  }
}

function assertOrdinaryFile(candidate: string, label: string): void {
  const stat = lstatSync(candidate);
  if (stat.isSymbolicLink() || !stat.isFile()) {
    fail(`${label} must be a regular file, not a link or special file.`);
  }
}

function databasePath(root: string, name: string): string {
  return path.join(root, 'data', name);
}

export function inspectColdMigration(homeDir: string): ColdMigrationPlan {
  const home = path.resolve(homeDir);
  const currentRoot = path.join(home, RECEIPTBI_DATA_DIRECTORY);
  const legacyRoot = path.join(home, LEGACY_DATA_DIRECTORY);
  const currentDatabase = databasePath(currentRoot, RECEIPTBI_DATABASE_NAME);
  const currentLegacyDatabase = databasePath(currentRoot, LEGACY_DATABASE_NAME);
  const legacyDatabase = databasePath(legacyRoot, LEGACY_DATABASE_NAME);

  assertDirectChild(home, currentRoot);
  assertDirectChild(home, legacyRoot);

  if (existsSync(currentRoot)) assertOrdinaryDirectory(currentRoot, 'ReceiptBI data root');
  if (existsSync(legacyRoot)) assertOrdinaryDirectory(legacyRoot, 'QueryGPT data root');

  if (existsSync(currentDatabase)) {
    assertOrdinaryFile(currentDatabase, 'ReceiptBI database');
    return {
      kind: 'none',
      sourceRoot: null,
      destinationRoot: currentRoot,
      sourceDatabase: null,
      destinationDatabase: currentDatabase,
      reason: 'ReceiptBI already has a current database.',
    };
  }

  if (existsSync(currentLegacyDatabase)) {
    assertOrdinaryFile(currentLegacyDatabase, 'legacy database');
    return {
      kind: 'legacy-database',
      sourceRoot: currentRoot,
      destinationRoot: currentRoot,
      sourceDatabase: currentLegacyDatabase,
      destinationDatabase: currentDatabase,
      reason: 'The current ReceiptBI root still uses the historical database name.',
    };
  }

  if (existsSync(currentRoot) && existsSync(legacyRoot)) {
    fail(
      'Both data roots exist but the ReceiptBI root has no database. Refusing to merge them automatically.'
    );
  }

  if (!existsSync(currentRoot) && existsSync(legacyRoot)) {
    if (!existsSync(legacyDatabase)) {
      fail('The QueryGPT data root exists but its database is missing.');
    }
    assertOrdinaryFile(legacyDatabase, 'legacy database');
    return {
      kind: 'legacy-root',
      sourceRoot: legacyRoot,
      destinationRoot: currentRoot,
      sourceDatabase: legacyDatabase,
      destinationDatabase: currentDatabase,
      reason: 'Only the historical QueryGPT data root exists.',
    };
  }

  return {
    kind: 'none',
    sourceRoot: null,
    destinationRoot: currentRoot,
    sourceDatabase: null,
    destinationDatabase: currentDatabase,
    reason: 'No historical desktop data was found.',
  };
}

function hashFile(filePath: string): { sha256: string; bytes: number } {
  const descriptor = openSync(filePath, 'r');
  const hash = createHash('sha256');
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  let bytes = 0;
  try {
    while (true) {
      const count = readSync(descriptor, buffer, 0, buffer.length, null);
      if (!count) break;
      bytes += count;
      hash.update(buffer.subarray(0, count));
    }
  } finally {
    closeSync(descriptor);
  }
  return { sha256: hash.digest('hex'), bytes };
}

function copyTree(source: string, destination: string, counter: { files: number }): void {
  assertOrdinaryDirectory(source, 'migration source directory');
  mkdirSync(destination, { mode: 0o700 });
  for (const entry of readdirSync(source, { withFileTypes: true })) {
    counter.files += 1;
    if (counter.files > MAX_FILE_COUNT) {
      fail(`The legacy data root contains more than ${MAX_FILE_COUNT} entries.`);
    }
    const sourceEntry = path.join(source, entry.name);
    const destinationEntry = path.join(destination, entry.name);
    const stat = lstatSync(sourceEntry);
    if (stat.isSymbolicLink()) {
      fail(`The legacy data root contains a symbolic link: ${entry.name}`);
    }
    if (stat.isDirectory()) {
      copyTree(sourceEntry, destinationEntry, counter);
      continue;
    }
    if (!stat.isFile()) {
      fail(`The legacy data root contains a special file: ${entry.name}`);
    }
    copyFileSync(sourceEntry, destinationEntry, fsConstants.COPYFILE_EXCL);
  }
}

function verifiedCopy(source: string, destination: string): { sha256: string; bytes: number } {
  assertOrdinaryFile(source, 'migration source database');
  copyFileSync(source, destination, fsConstants.COPYFILE_EXCL);
  const sourceHash = hashFile(source);
  const destinationHash = hashFile(destination);
  if (
    sourceHash.sha256 !== destinationHash.sha256 ||
    sourceHash.bytes !== destinationHash.bytes
  ) {
    fail('The copied database did not match the source byte for byte.');
  }
  return sourceHash;
}

function sqliteSidecars(database: string): string[] {
  return ['-wal', '-shm']
    .map((suffix) => `${database}${suffix}`)
    .filter((candidate) => existsSync(candidate));
}

function copySqliteSidecars(
  sourceDatabase: string,
  destinationDatabase: string
): readonly string[] {
  const copied: string[] = [];
  for (const source of sqliteSidecars(sourceDatabase)) {
    assertOrdinaryFile(source, 'SQLite sidecar');
    const suffix = source.slice(sourceDatabase.length);
    const destination = `${destinationDatabase}${suffix}`;
    verifiedCopy(source, destination);
    copied.push(suffix);
  }
  return copied;
}

function validateMigrationId(value: string): string {
  if (!/^[a-zA-Z0-9][a-zA-Z0-9-]{7,63}$/.test(value)) {
    fail('The migration identifier is invalid.');
  }
  return value;
}

export function executeColdMigration(
  homeDir: string,
  options: ColdMigrationOptions
): ColdMigrationReceipt | null {
  if (!options.legacyAppClosed) {
    fail('Close QueryGPT before running the cold migration.');
  }

  const plan = inspectColdMigration(homeDir);
  if (plan.kind === 'none') return null;
  if (!plan.sourceRoot || !plan.sourceDatabase) {
    fail('The migration plan is incomplete.');
  }

  const migrationId = validateMigrationId(options.migrationId || randomUUID());
  const home = path.resolve(homeDir);
  const backupBase = path.join(home, BACKUP_DIRECTORY);
  const backupRoot = path.join(backupBase, migrationId);
  const backupDatabase = path.join(backupRoot, LEGACY_DATABASE_NAME);
  assertDirectChild(home, backupBase);
  if (existsSync(backupBase)) {
    assertOrdinaryDirectory(backupBase, 'migration backup root');
  } else {
    mkdirSync(backupBase, { mode: 0o700 });
  }
  if (existsSync(backupRoot)) fail('The migration backup already exists.');
  mkdirSync(backupRoot, { mode: 0o700 });
  const sourceHash = verifiedCopy(plan.sourceDatabase, backupDatabase);
  const sqliteSidecars = copySqliteSidecars(plan.sourceDatabase, backupDatabase);

  if (plan.kind === 'legacy-root') {
    const stagingRoot = `${plan.destinationRoot}.migration-${migrationId}`;
    assertDirectChild(home, stagingRoot);
    if (existsSync(plan.destinationRoot) || existsSync(stagingRoot)) {
      fail('The ReceiptBI destination became occupied during migration.');
    }
    copyTree(plan.sourceRoot, stagingRoot, { files: 0 });
    const stagedLegacyDatabase = databasePath(stagingRoot, LEGACY_DATABASE_NAME);
    const stagedCurrentDatabase = databasePath(stagingRoot, RECEIPTBI_DATABASE_NAME);
    assertOrdinaryFile(stagedLegacyDatabase, 'staged legacy database');
    renameSync(stagedLegacyDatabase, stagedCurrentDatabase);
    for (const suffix of sqliteSidecars) {
      const legacySidecar = `${stagedLegacyDatabase}${suffix}`;
      const currentSidecar = `${stagedCurrentDatabase}${suffix}`;
      assertOrdinaryFile(legacySidecar, 'staged SQLite sidecar');
      renameSync(legacySidecar, currentSidecar);
    }
    const stagedHash = hashFile(stagedCurrentDatabase);
    if (stagedHash.sha256 !== sourceHash.sha256 || stagedHash.bytes !== sourceHash.bytes) {
      fail('The staged ReceiptBI database did not match the historical source.');
    }
    renameSync(stagingRoot, plan.destinationRoot);
  } else {
    mkdirSync(path.dirname(plan.destinationDatabase), { recursive: true, mode: 0o700 });
    const stagedDatabase = `${plan.destinationDatabase}.migration-${migrationId}`;
    const stagedHash = verifiedCopy(plan.sourceDatabase, stagedDatabase);
    const stagedSidecars = copySqliteSidecars(plan.sourceDatabase, stagedDatabase);
    if (stagedHash.sha256 !== sourceHash.sha256 || stagedHash.bytes !== sourceHash.bytes) {
      fail('The staged ReceiptBI database did not match the historical source.');
    }
    if (existsSync(plan.destinationDatabase)) {
      fail('The ReceiptBI database became occupied during migration.');
    }
    renameSync(stagedDatabase, plan.destinationDatabase);
    for (const suffix of stagedSidecars) {
      renameSync(`${stagedDatabase}${suffix}`, `${plan.destinationDatabase}${suffix}`);
    }
  }

  const destinationHash = hashFile(plan.destinationDatabase);
  if (
    destinationHash.sha256 !== sourceHash.sha256 ||
    destinationHash.bytes !== sourceHash.bytes
  ) {
    fail('The final ReceiptBI database did not match the historical source.');
  }

  const receipt: ColdMigrationReceipt = {
    version: 1,
    migrationId,
    kind: plan.kind,
    createdAt: (options.now || new Date()).toISOString(),
    sourceRoot: plan.sourceRoot,
    destinationRoot: plan.destinationRoot,
    sourceDatabase: plan.sourceDatabase,
    destinationDatabase: plan.destinationDatabase,
    backupDatabase,
    databaseBytes: sourceHash.bytes,
    databaseSha256: sourceHash.sha256,
    sqliteSidecars,
    sourcePreserved: true,
    backupPreserved: true,
  };
  writeFileSync(
    path.join(plan.destinationRoot, RECEIPT_FILE),
    `${JSON.stringify(receipt, null, 2)}\n`,
    { encoding: 'utf8', flag: 'wx', mode: 0o600 }
  );
  return receipt;
}

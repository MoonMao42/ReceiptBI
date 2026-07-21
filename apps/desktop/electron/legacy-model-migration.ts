import { createHash, randomUUID } from 'node:crypto';
import {
  chmodSync,
  closeSync,
  constants,
  fstatSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readSync,
  realpathSync,
  renameSync,
  unlinkSync,
  writeFileSync,
  writeSync,
  type Stats,
} from 'node:fs';
import path from 'node:path';

const MIGRATION_VERSION = 2 as const;
const STATE_FILE_NAME = 'state.json';
const SNAPSHOT_FILE_NAME = 'model-config.sqlite3';
const ENVIRONMENT_BACKUP_FILE_NAME = 'environment.backup';
const MAX_STATE_BYTES = 64 * 1024;
const MAX_ENV_BYTES = 1024 * 1024;
const COPY_BUFFER_BYTES = 64 * 1024;
const PRIVATE_DIRECTORY_MODE = 0o700;
const PRIVATE_FILE_MODE = 0o600;
const NO_FOLLOW = process.platform === 'win32' ? 0 : (constants.O_NOFOLLOW ?? 0);

export const LEGACY_MODEL_DATABASE_RELATIVE_PATH = path.join(
  'data',
  'querygpt-ts.db'
);
export const LEGACY_MODEL_MIGRATION_BACKUP_RELATIVE_DIRECTORY = path.join(
  'migration-backups',
  'legacy-model-config'
);

type MigrationStatus = 'prepared' | 'imported';

interface EnvironmentBackupManifest {
  readonly bytes: number;
  readonly sha256: string;
}

interface MigrationManifest {
  readonly version: typeof MIGRATION_VERSION;
  readonly migrationId: string;
  readonly status: MigrationStatus;
  readonly environmentBackup: EnvironmentBackupManifest | null;
}

interface PreparedRoot {
  readonly lexicalPath: string;
  readonly realPath: string;
}

export class LegacyModelMigrationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'LegacyModelMigrationError';
  }
}

export type LegacyModelMigrationPreparation =
  | { readonly status: 'absent' }
  | {
      readonly status: 'ready';
      readonly migrationId: string;
      /**
       * The fixed active legacy database path, or null when a backend-created
       * snapshot is available after the active source disappeared.
       */
      readonly databaseSourcePath: string | null;
      /**
       * A private, initially absent target. Only the backend may populate it,
       * using SQLite's backup API and atomic publication.
       */
      readonly databaseSnapshotPath: string;
      readonly legacyEncryptionKey: string | null;
    }
  | { readonly status: 'imported'; readonly migrationId: string };

export type LegacyModelMigrationAckStatus = 'imported' | 'already_present' | 'empty';

/** Validate the backend's commit ACK before recording the imported marker. */
export function validateLegacyModelMigrationAck(
  rawAck: unknown,
  expectedInstanceToken: string
): LegacyModelMigrationAckStatus {
  if (!rawAck || typeof rawAck !== 'object' || Array.isArray(rawAck)) {
    fail('The backend did not acknowledge the legacy model migration.');
  }
  const ack = rawAck as { status?: unknown; instance_token?: unknown };
  if (ack.instance_token !== expectedInstanceToken) {
    fail('The legacy model migration acknowledgement is not from this launch.');
  }
  if (!['imported', 'already_present', 'empty'].includes(String(ack.status))) {
    fail('The backend returned an invalid legacy model migration acknowledgement.');
  }
  return ack.status as LegacyModelMigrationAckStatus;
}

function isFileSystemError(error: unknown, code: string): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    (error as NodeJS.ErrnoException).code === code
  );
}

function fail(message: string): never {
  throw new LegacyModelMigrationError(message);
}

function withoutFileSystemDetails<T>(
  operation: () => T,
  fallbackMessage: string
): T {
  try {
    return operation();
  } catch (error) {
    if (error instanceof LegacyModelMigrationError) throw error;
    throw new LegacyModelMigrationError(fallbackMessage);
  }
}

function optionalLstat(candidate: string): Stats | null {
  try {
    return lstatSync(candidate);
  } catch (error) {
    if (isFileSystemError(error, 'ENOENT')) return null;
    throw error;
  }
}

function isContained(parent: string, candidate: string): boolean {
  const relative = path.relative(parent, candidate);
  return (
    relative === '' ||
    (!relative.startsWith(`..${path.sep}`) &&
      relative !== '..' &&
      !path.isAbsolute(relative))
  );
}

function preparedRoot(userDataDir: string): PreparedRoot {
  if (!path.isAbsolute(userDataDir)) {
    fail('The prepared desktop data directory is invalid.');
  }

  const lexicalPath = path.resolve(userDataDir);
  const rootStats = optionalLstat(lexicalPath);
  if (!rootStats || rootStats.isSymbolicLink() || !rootStats.isDirectory()) {
    fail('The prepared desktop data directory is unsafe.');
  }

  return { lexicalPath, realPath: realpathSync.native(lexicalPath) };
}

function assertRealPathContained(root: PreparedRoot, candidate: string): void {
  const resolved = realpathSync.native(candidate);
  if (!isContained(root.realPath, resolved)) {
    fail('A legacy migration path escaped the prepared desktop data directory.');
  }
}

function inspectDirectoryChain(
  root: PreparedRoot,
  segments: readonly string[],
  options: { readonly create: boolean; readonly privateMode: boolean }
): string | null {
  let current = root.lexicalPath;

  for (const segment of segments) {
    if (!segment || segment === '.' || segment === '..' || segment.includes(path.sep)) {
      fail('A legacy migration directory is invalid.');
    }

    current = path.join(current, segment);
    let stats = optionalLstat(current);
    if (!stats) {
      if (!options.create) return null;
      try {
        mkdirSync(current, { mode: PRIVATE_DIRECTORY_MODE });
      } catch (error) {
        if (!isFileSystemError(error, 'EEXIST')) throw error;
      }
      stats = optionalLstat(current);
    }

    if (!stats || stats.isSymbolicLink() || !stats.isDirectory()) {
      fail('A legacy migration directory is unsafe.');
    }
    assertRealPathContained(root, current);

    if (options.privateMode && process.platform !== 'win32') {
      if (options.create) {
        chmodSync(current, PRIVATE_DIRECTORY_MODE);
      } else if ((stats.mode & 0o077) !== 0) {
        fail('A legacy migration directory is not private.');
      }
    }
  }

  return current;
}

function inspectActiveRegularFile(
  root: PreparedRoot,
  segments: readonly string[]
): string | null {
  const parentSegments = segments.slice(0, -1);
  if (
    parentSegments.length > 0 &&
    !inspectDirectoryChain(root, parentSegments, {
      create: false,
      privateMode: false,
    })
  ) {
    return null;
  }

  const candidate = path.join(root.lexicalPath, ...segments);
  if (!isContained(root.lexicalPath, path.resolve(candidate))) {
    fail('A legacy migration source escaped the prepared desktop data directory.');
  }
  const stats = optionalLstat(candidate);
  if (!stats) return null;
  if (stats.isSymbolicLink() || !stats.isFile()) {
    fail('A legacy migration source is not a regular file.');
  }
  assertRealPathContained(root, candidate);
  return candidate;
}

function inspectActiveDatabase(root: PreparedRoot): string | null {
  return inspectActiveRegularFile(root, ['data', 'querygpt-ts.db']);
}

function inspectActiveEnvironment(root: PreparedRoot): string | null {
  return inspectActiveRegularFile(root, ['.env']);
}

function openRegularFileForRead(candidate: string): number {
  const descriptor = openSync(candidate, constants.O_RDONLY | NO_FOLLOW);
  const stats = fstatSync(descriptor);
  if (!stats.isFile()) {
    closeSync(descriptor);
    fail('A legacy migration file is not regular.');
  }
  return descriptor;
}

function digestRegularFile(candidate: string): EnvironmentBackupManifest {
  const descriptor = openRegularFileForRead(candidate);
  const hash = createHash('sha256');
  const buffer = Buffer.allocUnsafe(COPY_BUFFER_BYTES);
  let bytes = 0;

  try {
    for (;;) {
      const read = readSync(descriptor, buffer, 0, buffer.length, null);
      if (read === 0) break;
      hash.update(buffer.subarray(0, read));
      bytes += read;
    }
  } finally {
    closeSync(descriptor);
  }

  return { bytes, sha256: hash.digest('hex') };
}

function sameStableFile(before: Stats, after: Stats): boolean {
  return (
    before.dev === after.dev &&
    before.ino === after.ino &&
    before.size === after.size &&
    before.mtimeMs === after.mtimeMs &&
    before.ctimeMs === after.ctimeMs
  );
}

function writeAll(descriptor: number, buffer: Buffer): void {
  let offset = 0;
  while (offset < buffer.length) {
    offset += writeSync(descriptor, buffer, offset, buffer.length - offset, null);
  }
}

function copyEnvironmentBackupExclusive(
  source: string,
  destination: string
): EnvironmentBackupManifest {
  let sourceDescriptor: number | null = null;
  let destinationDescriptor: number | null = null;
  let destinationCreated = false;

  try {
    sourceDescriptor = openRegularFileForRead(source);
    const before = fstatSync(sourceDescriptor);
    if (before.size > MAX_ENV_BYTES) {
      fail('The legacy environment backup is too large.');
    }
    destinationDescriptor = openSync(
      destination,
      constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL,
      PRIVATE_FILE_MODE
    );
    destinationCreated = true;

    const hash = createHash('sha256');
    const buffer = Buffer.allocUnsafe(COPY_BUFFER_BYTES);
    let bytes = 0;
    for (;;) {
      const read = readSync(sourceDescriptor, buffer, 0, buffer.length, null);
      if (read === 0) break;
      const chunk = buffer.subarray(0, read);
      hash.update(chunk);
      writeAll(destinationDescriptor, chunk);
      bytes += read;
    }

    fsyncSync(destinationDescriptor);
    const after = fstatSync(sourceDescriptor);
    if (!sameStableFile(before, after) || bytes !== before.size) {
      fail('The legacy environment changed while it was being backed up.');
    }
    if (process.platform !== 'win32') chmodSync(destination, PRIVATE_FILE_MODE);
    return { bytes, sha256: hash.digest('hex') };
  } catch (error) {
    if (destinationDescriptor !== null) {
      try {
        closeSync(destinationDescriptor);
      } catch {
        // The public wrapper deliberately omits filesystem details.
      }
      destinationDescriptor = null;
    }
    if (destinationCreated) {
      try {
        unlinkSync(destination);
      } catch {
        // Only the unpublished environment backup can be removed here.
      }
    }
    throw error;
  } finally {
    if (destinationDescriptor !== null) closeSync(destinationDescriptor);
    if (sourceDescriptor !== null) closeSync(sourceDescriptor);
  }
}

function readRegularText(candidate: string, maximumBytes: number): string {
  const descriptor = openRegularFileForRead(candidate);
  try {
    const stats = fstatSync(descriptor);
    if (stats.size > maximumBytes) {
      fail('A legacy migration text file is too large.');
    }
    const content = readFileSync(descriptor, 'utf-8');
    if (Buffer.byteLength(content, 'utf-8') > maximumBytes) {
      fail('A legacy migration text file is too large.');
    }
    return content;
  } finally {
    closeSync(descriptor);
  }
}

function backupBase(root: PreparedRoot, create: boolean): string | null {
  return inspectDirectoryChain(
    root,
    ['migration-backups', 'legacy-model-config'],
    { create, privateMode: true }
  );
}

function statePath(root: PreparedRoot, createBase: boolean): string | null {
  const base = backupBase(root, createBase);
  return base ? path.join(base, STATE_FILE_NAME) : null;
}

function validateMigrationId(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
      value
    )
  );
}

function parseEnvironmentBackup(value: unknown): EnvironmentBackupManifest | null {
  if (value === null) return null;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    fail('The legacy migration state is invalid.');
  }
  const candidate = value as Record<string, unknown>;
  if (
    !Number.isSafeInteger(candidate.bytes) ||
    Number(candidate.bytes) < 0 ||
    Number(candidate.bytes) > MAX_ENV_BYTES ||
    typeof candidate.sha256 !== 'string' ||
    !/^[0-9a-f]{64}$/.test(candidate.sha256)
  ) {
    fail('The legacy migration state is invalid.');
  }
  return { bytes: Number(candidate.bytes), sha256: candidate.sha256 };
}

function parseManifest(raw: string): MigrationManifest {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    fail('The legacy migration state is invalid.');
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    fail('The legacy migration state is invalid.');
  }
  const candidate = parsed as Record<string, unknown>;
  if (
    candidate.version !== MIGRATION_VERSION ||
    !validateMigrationId(candidate.migrationId) ||
    !['prepared', 'imported'].includes(String(candidate.status)) ||
    !Object.hasOwn(candidate, 'environmentBackup')
  ) {
    fail('The legacy migration state is invalid.');
  }

  return {
    version: MIGRATION_VERSION,
    migrationId: candidate.migrationId,
    status: candidate.status as MigrationStatus,
    environmentBackup: parseEnvironmentBackup(candidate.environmentBackup),
  };
}

function readManifest(root: PreparedRoot): MigrationManifest | null {
  const candidate = statePath(root, false);
  if (!candidate) return null;

  const stats = optionalLstat(candidate);
  if (!stats) return null;
  if (stats.isSymbolicLink() || !stats.isFile()) {
    fail('The legacy migration state is unsafe.');
  }
  assertRealPathContained(root, candidate);
  if (process.platform !== 'win32' && (stats.mode & 0o077) !== 0) {
    fail('The legacy migration state is not private.');
  }
  return parseManifest(readRegularText(candidate, MAX_STATE_BYTES));
}

function writeManifestAtomic(
  root: PreparedRoot,
  manifest: MigrationManifest
): void {
  const destination = statePath(root, true);
  if (!destination) fail('The legacy migration state directory is unavailable.');

  const existing = optionalLstat(destination);
  if (existing && (existing.isSymbolicLink() || !existing.isFile())) {
    fail('The legacy migration state is unsafe.');
  }

  const temporary = path.join(path.dirname(destination), `.state-${randomUUID()}.tmp`);
  let descriptor: number | null = null;
  let created = false;
  try {
    descriptor = openSync(
      temporary,
      constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL,
      PRIVATE_FILE_MODE
    );
    created = true;
    writeFileSync(descriptor, `${JSON.stringify(manifest)}\n`, 'utf-8');
    fsyncSync(descriptor);
    closeSync(descriptor);
    descriptor = null;
    if (process.platform !== 'win32') chmodSync(temporary, PRIVATE_FILE_MODE);
    renameSync(temporary, destination);
    created = false;
    if (process.platform !== 'win32') chmodSync(destination, PRIVATE_FILE_MODE);
  } finally {
    if (descriptor !== null) closeSync(descriptor);
    if (created) {
      try {
        unlinkSync(temporary);
      } catch {
        // The temporary contains only non-secret state and is private.
      }
    }
  }
}

function createArchiveDirectory(
  root: PreparedRoot
): { migrationId: string; directory: string } {
  const base = backupBase(root, true);
  if (!base) fail('The legacy migration archive directory is unavailable.');

  for (let attempt = 0; attempt < 16; attempt += 1) {
    const migrationId = randomUUID();
    const directory = path.join(base, migrationId);
    try {
      mkdirSync(directory, { mode: PRIVATE_DIRECTORY_MODE });
    } catch (error) {
      if (isFileSystemError(error, 'EEXIST')) continue;
      throw error;
    }
    assertRealPathContained(root, directory);
    if (process.platform !== 'win32') chmodSync(directory, PRIVATE_DIRECTORY_MODE);
    return { migrationId, directory };
  }

  fail('A unique legacy migration archive could not be created.');
}

function archiveDirectory(root: PreparedRoot, migrationId: string): string {
  if (!validateMigrationId(migrationId)) {
    fail('The legacy migration identifier is invalid.');
  }
  const base = backupBase(root, false);
  if (!base) fail('The legacy migration archive is missing.');
  const directory = path.join(base, migrationId);
  const stats = optionalLstat(directory);
  if (!stats || stats.isSymbolicLink() || !stats.isDirectory()) {
    fail('The legacy migration archive is unsafe.');
  }
  assertRealPathContained(root, directory);
  if (process.platform !== 'win32' && (stats.mode & 0o077) !== 0) {
    fail('The legacy migration archive is not private.');
  }
  return directory;
}

function environmentBackupPath(
  root: PreparedRoot,
  manifest: MigrationManifest
): string {
  return path.join(
    archiveDirectory(root, manifest.migrationId),
    ENVIRONMENT_BACKUP_FILE_NAME
  );
}

function databaseSnapshotPath(
  root: PreparedRoot,
  manifest: MigrationManifest
): string {
  return path.join(archiveDirectory(root, manifest.migrationId), SNAPSHOT_FILE_NAME);
}

function verifyEnvironmentBackup(
  root: PreparedRoot,
  manifest: MigrationManifest
): void {
  const candidate = environmentBackupPath(root, manifest);
  const stats = optionalLstat(candidate);
  if (!manifest.environmentBackup) {
    if (stats) fail('The legacy environment archive is unexpected.');
    return;
  }
  if (!stats || stats.isSymbolicLink() || !stats.isFile()) {
    fail('The legacy environment archive verification failed.');
  }
  assertRealPathContained(root, candidate);
  if (process.platform !== 'win32' && (stats.mode & 0o077) !== 0) {
    fail('The legacy environment archive is not private.');
  }
  const digest = digestRegularFile(candidate);
  if (
    digest.bytes !== manifest.environmentBackup.bytes ||
    digest.sha256 !== manifest.environmentBackup.sha256
  ) {
    fail('The legacy environment archive verification failed.');
  }
}

function inspectDatabaseSnapshot(
  root: PreparedRoot,
  manifest: MigrationManifest
): string | null {
  const candidate = databaseSnapshotPath(root, manifest);
  const stats = optionalLstat(candidate);
  if (!stats) return null;
  if (stats.isSymbolicLink() || !stats.isFile()) {
    fail('The backend-created legacy model snapshot is unsafe.');
  }
  assertRealPathContained(root, candidate);
  if (process.platform !== 'win32' && (stats.mode & 0o077) !== 0) {
    fail('The backend-created legacy model snapshot is not private.');
  }
  return candidate;
}

function parseAssignmentValue(raw: string): string {
  const value = raw.trim();
  if (value.startsWith('"')) {
    const match = value.match(/^"((?:\\.|[^"\\])*)"/);
    if (!match) return value;
    return match[1].replace(/\\([\\"])/g, '$1');
  }
  if (value.startsWith("'")) {
    const closingQuote = value.indexOf("'", 1);
    return closingQuote < 0 ? value : value.slice(1, closingQuote);
  }
  return value.split('#', 1)[0].trim();
}

function isValidLegacyEncryptionKey(value: string): boolean {
  if (!/^[A-Za-z0-9_-]{43}=?$/.test(value)) return false;
  const unpadded = value.replace(/=+$/, '');
  const padded = `${unpadded}${'='.repeat((4 - (unpadded.length % 4)) % 4)}`;
  return Buffer.from(
    padded.replace(/-/g, '+').replace(/_/g, '/'),
    'base64'
  ).length === 32;
}

function readArchivedEncryptionKey(
  root: PreparedRoot,
  manifest: MigrationManifest
): string | null {
  if (!manifest.environmentBackup) return null;

  const content = readRegularText(
    environmentBackupPath(root, manifest),
    MAX_ENV_BYTES
  );
  let candidate: string | null = null;
  for (const line of content.split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?ENCRYPTION_KEY\s*=\s*(.*?)\s*$/);
    if (!match) continue;
    candidate = parseAssignmentValue(match[1]);
  }

  if (candidate !== null && !isValidLegacyEncryptionKey(candidate)) {
    fail('The legacy encryption key is invalid.');
  }
  return candidate;
}

function readyPreparation(
  root: PreparedRoot,
  manifest: MigrationManifest
): LegacyModelMigrationPreparation {
  verifyEnvironmentBackup(root, manifest);
  const source = inspectActiveDatabase(root);
  const snapshot = inspectDatabaseSnapshot(root, manifest);
  if (!source && !snapshot) {
    fail('Neither the legacy model source nor its backend snapshot is available.');
  }
  return {
    status: 'ready',
    migrationId: manifest.migrationId,
    databaseSourcePath: source,
    databaseSnapshotPath: databaseSnapshotPath(root, manifest),
    legacyEncryptionKey: readArchivedEncryptionKey(root, manifest),
  };
}

function prepareLegacyModelMigrationImpl(
  userDataDir: string
): LegacyModelMigrationPreparation {
  const root = preparedRoot(userDataDir);
  const existingManifest = readManifest(root);

  if (existingManifest) {
    verifyEnvironmentBackup(root, existingManifest);
    const snapshot = inspectDatabaseSnapshot(root, existingManifest);
    if (existingManifest.status === 'imported') {
      if (!snapshot) {
        fail('The imported legacy model snapshot is missing.');
      }
      return { status: 'imported', migrationId: existingManifest.migrationId };
    }
    return readyPreparation(root, existingManifest);
  }

  const source = inspectActiveDatabase(root);
  if (!source) {
    // A credential by itself is not migration authority. In particular, do not
    // inspect or parse .env when the legacy database is absent.
    return { status: 'absent' };
  }

  const archive = createArchiveDirectory(root);
  const environment = inspectActiveEnvironment(root);
  const environmentBackup = environment
    ? copyEnvironmentBackupExclusive(
        environment,
        path.join(archive.directory, ENVIRONMENT_BACKUP_FILE_NAME)
      )
    : null;
  const manifest: MigrationManifest = {
    version: MIGRATION_VERSION,
    migrationId: archive.migrationId,
    status: 'prepared',
    environmentBackup,
  };
  verifyEnvironmentBackup(root, manifest);
  writeManifestAtomic(root, manifest);
  return readyPreparation(root, manifest);
}

/**
 * Reserve a private backend snapshot target and back up only the legacy .env.
 * SQLite files are never copied, renamed, linked, deleted, or opened here.
 */
export function prepareLegacyModelMigration(
  userDataDir: string
): LegacyModelMigrationPreparation {
  return withoutFileSystemDetails(
    () => prepareLegacyModelMigrationImpl(userDataDir),
    'The legacy model migration could not be prepared safely.'
  );
}

function requireMatchingManifest(
  root: PreparedRoot,
  migrationId: string
): MigrationManifest {
  const manifest = readManifest(root);
  if (!manifest || manifest.migrationId !== migrationId) {
    fail('The legacy migration acknowledgement does not match the prepared state.');
  }
  return manifest;
}

/** Mark a successful backend import ACK without storing credentials or paths. */
export function markLegacyModelMigrationImported(
  userDataDir: string,
  migrationId: string
): { readonly status: 'imported'; readonly migrationId: string } {
  return withoutFileSystemDetails(
    () => {
      const root = preparedRoot(userDataDir);
      const manifest = requireMatchingManifest(root, migrationId);
      verifyEnvironmentBackup(root, manifest);
      if (!inspectDatabaseSnapshot(root, manifest)) {
        fail('The backend-created legacy model snapshot is missing.');
      }
      if (manifest.status === 'prepared') {
        writeManifestAtomic(root, { ...manifest, status: 'imported' });
      }
      return { status: 'imported' as const, migrationId };
    },
    'The legacy model import acknowledgement could not be recorded safely.'
  );
}

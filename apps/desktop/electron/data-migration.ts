import { existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';

export const RECEIPTBI_DATA_DIRECTORY = '.receiptbi-desktop';
export const LEGACY_DATA_DIRECTORY = '.querygpt-desktop';
export const RECEIPTBI_DATABASE_NAME = 'receiptbi.db';
export const LEGACY_DATABASE_NAME = 'querygpt.db';

export type DesktopDataMigrationKind = 'new' | 'current' | 'coexisting';

export interface DesktopDataPaths {
  readonly userDataDir: string;
  readonly dataDir: string;
  readonly databasePath: string;
  readonly migrationKind: DesktopDataMigrationKind;
  readonly events: readonly string[];
}

export class LegacyDataMigrationRequiredError extends Error {
  constructor(scope: 'data-directory' | 'database') {
    const subject =
      scope === 'data-directory'
        ? 'legacy QueryGPT data directory'
        : `legacy ${LEGACY_DATABASE_NAME} database`;
    super(
      `The ${subject} requires a cold migration. Close the legacy application, create a verified backup, and complete the cold migration before starting ReceiptBI.`
    );
    this.name = 'LegacyDataMigrationRequiredError';
  }
}

function resolveCurrentDatabasePath(dataDir: string, events: string[]): string {
  const currentDatabase = path.join(dataDir, RECEIPTBI_DATABASE_NAME);
  const legacyDatabase = path.join(dataDir, LEGACY_DATABASE_NAME);
  const currentExists = existsSync(currentDatabase);
  const legacyExists = existsSync(legacyDatabase);

  if (currentExists) {
    if (legacyExists) {
      events.push(
        `Both database names exist; using ${RECEIPTBI_DATABASE_NAME} without changing ${LEGACY_DATABASE_NAME}`
      );
    }
    return currentDatabase;
  }

  if (legacyExists) {
    throw new LegacyDataMigrationRequiredError('database');
  }

  mkdirSync(dataDir, { recursive: true });
  return currentDatabase;
}

/**
 * Select the current ReceiptBI state without mutating historical QueryGPT
 * state. Any layout that needs a move or rename is rejected so migration can
 * happen only as an explicit, backed-up cold operation.
 */
export async function prepareDesktopDataPaths(
  homeDir: string
): Promise<DesktopDataPaths> {
  const currentDir = path.join(homeDir, RECEIPTBI_DATA_DIRECTORY);
  const legacyDir = path.join(homeDir, LEGACY_DATA_DIRECTORY);
  const currentExists = existsSync(currentDir);
  const legacyExists = existsSync(legacyDir);

  if (!currentExists && legacyExists) {
    throw new LegacyDataMigrationRequiredError('data-directory');
  }

  const events: string[] = [];
  let migrationKind: DesktopDataMigrationKind;
  if (!currentExists) {
    mkdirSync(currentDir, { recursive: true });
    migrationKind = 'new';
    events.push('Created the ReceiptBI desktop data directory');
  } else if (legacyExists) {
    migrationKind = 'coexisting';
    events.push(
      'Current and legacy desktop data both exist; using ReceiptBI data without changing either directory'
    );
  } else {
    migrationKind = 'current';
  }

  const dataDir = path.join(currentDir, 'data');
  const databasePath = resolveCurrentDatabasePath(dataDir, events);

  return {
    userDataDir: currentDir,
    dataDir,
    databasePath,
    migrationKind,
    events,
  };
}

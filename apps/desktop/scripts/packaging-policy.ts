import { existsSync, lstatSync, readlinkSync, readdirSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';

const FORBIDDEN_DIRECTORY_NAMES = new Set(['projects', 'backups', '.python']);
const DATABASE_FILE_PATTERN =
  /(?:\.(?:db|sqlite|sqlite3)(?:-(?:journal|shm|wal))?|\.(?:ddb|duckdb)(?:\.wal)?)$/i;

function isForbiddenFile(name: string): boolean {
  const normalizedName = name.toLowerCase();
  if (
    normalizedName === '.env'
    || (normalizedName.startsWith('.env.') && normalizedName !== '.env.example')
  ) {
    return true;
  }
  return DATABASE_FILE_PATTERN.test(name);
}

/**
 * Release resources are immutable program files. User workspaces, databases,
 * credentials, and dependency environments belong in Electron's user-data
 * directory and must never be copied into an installer.
 */
function collectViolations(bundleRoot: string, rejectRuntimeDirectories: boolean): string[] {
  if (!existsSync(bundleRoot)) {
    throw new Error('bundle is missing');
  }

  const resolvedBundleRoot = resolve(bundleRoot);
  const violations: string[] = [];
  const visit = (directory: string): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const fullPath = join(directory, entry.name);
      const relativePath = relative(bundleRoot, fullPath);
      const portableRelativePath = relativePath.split(/[\\/]+/).join('/');
      const normalizedDirectoryName = entry.name.toLowerCase();
      const normalizedRelativePath = portableRelativePath.toLowerCase();
      const isDirectoryOrLink = entry.isDirectory() || entry.isSymbolicLink();

      if (
        rejectRuntimeDirectories
        && isDirectoryOrLink
        && (
          FORBIDDEN_DIRECTORY_NAMES.has(normalizedDirectoryName)
          || normalizedRelativePath === 'data'
          || normalizedRelativePath === '_internal/data'
        )
      ) {
        violations.push(relativePath);
        continue;
      }
      if ((entry.isFile() || entry.isSymbolicLink()) && isForbiddenFile(entry.name)) {
        violations.push(relativePath);
        continue;
      }
      if (entry.isSymbolicLink()) {
        const target = resolve(dirname(fullPath), readlinkSync(fullPath));
        const targetRelativePath = relative(resolvedBundleRoot, target);
        if (
          targetRelativePath === '..'
          || targetRelativePath.startsWith(`..${sep}`)
          || isAbsolute(targetRelativePath)
        ) {
          violations.push(relativePath);
        }
        continue;
      }
      if (entry.isDirectory() && !entry.isSymbolicLink() && !lstatSync(fullPath).isSymbolicLink()) {
        visit(fullPath);
      }
    }
  };

  visit(bundleRoot);
  return violations;
}

function assertNoViolations(violations: string[], label: string): void {
  if (violations.length > 0) {
    throw new Error(
      `${label} contains runtime-only data: ${violations.slice(0, 20).join(', ')}`
    );
  }
}

export function assertNoBundledRuntimeData(bundleRoot: string, label = 'bundle'): void {
  assertNoViolations(collectViolations(bundleRoot, true), label);
}

export function assertNoBundledSensitiveFiles(bundleRoot: string, label = 'bundle'): void {
  assertNoViolations(collectViolations(bundleRoot, false), label);
}

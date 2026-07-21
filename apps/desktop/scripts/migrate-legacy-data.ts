import os from 'node:os';
import path from 'node:path';
import {
  executeColdMigration,
  inspectColdMigration,
} from '../electron/cold-data-migration.js';

function argumentValue(name: string): string | null {
  const index = process.argv.indexOf(name);
  if (index < 0) return null;
  const value = process.argv[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`${name} requires a value.`);
  }
  return value;
}

const homeDir = path.resolve(argumentValue('--home') || os.homedir());
const execute = process.argv.includes('--execute');
const acknowledged = process.argv.includes('--acknowledge-legacy-app-closed');
const plan = inspectColdMigration(homeDir);

if (!execute) {
  process.stdout.write(
    `${JSON.stringify(
      {
        mode: 'inspection',
        plan,
        next:
          plan.kind === 'none'
            ? null
            : 'Close QueryGPT, verify the paths above, then rerun with --execute --acknowledge-legacy-app-closed.',
      },
      null,
      2
    )}\n`
  );
  process.exit(0);
}

const receipt = executeColdMigration(homeDir, {
  legacyAppClosed: acknowledged,
});
process.stdout.write(
  `${JSON.stringify(
    receipt
      ? { mode: 'executed', receipt }
      : { mode: 'no-op', reason: plan.reason },
    null,
    2
  )}\n`
);

#!/usr/bin/env tsx

import { dirname, resolve } from 'node:path';
import {
  assertNoBundledRuntimeData,
  assertNoBundledSensitiveFiles,
} from './packaging-policy.js';

const backendRoot = process.argv[2];
if (!backendRoot) {
  throw new Error('Usage: verify-packaged-resources.ts <packaged-backend-directory>');
}

const resolvedBackendRoot = resolve(backendRoot);
assertNoBundledRuntimeData(resolvedBackendRoot, 'packaged backend resources');
assertNoBundledSensitiveFiles(dirname(resolvedBackendRoot), 'packaged application resources');
console.log('Packaged desktop resources contain no runtime project data.');

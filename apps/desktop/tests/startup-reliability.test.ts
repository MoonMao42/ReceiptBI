import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  ChunkLoadRecoveryGate,
  describeChunkLoadFailure,
  extractNextStaticScriptUrls,
  isHtmlContentType,
  isJavaScriptContentType,
  isNextStaticScriptUrl,
  isRendererChunkFailureReport,
} from '../electron/frontend-reliability.js';
import {
  validateFrontendBundle,
  writeFrontendBuildManifest,
} from '../electron/frontend-bundle.js';

test('only concrete Next.js chunk failures enter recovery', () => {
  assert.deepEqual(
    describeChunkLoadFailure({
      name: 'ChunkLoadError',
      message: 'Loading chunk 472 failed. (error: http://127.0.0.1/_next/static/chunks/472.js)',
    }),
    {
      kind: 'chunk-load',
      name: 'ChunkLoadError',
      message: 'Loading chunk 472 failed. (error: http://127.0.0.1/_next/static/chunks/472.js)',
    }
  );
  assert.equal(
    describeChunkLoadFailure(new Error('A component render failed')),
    null
  );
  assert.equal(
    describeChunkLoadFailure({ name: 'TypeError', message: 'Failed to fetch' }),
    null
  );
});

test('chunk recovery reloads once, deduplicates a document, then becomes terminal', () => {
  const gate = new ChunkLoadRecoveryGate();
  const firstDocument = '2d931510-d99f-4fe7-86c2-0f86d4cbe7a5';
  const secondDocument = 'bbdb8724-0f3a-49e2-ad56-b3a39e7c5a35';

  assert.equal(gate.recordFailure(firstDocument), 'reload');
  assert.equal(gate.recordFailure(firstDocument), 'ignore');
  assert.equal(gate.recordFailure(secondDocument), 'show-error');
  assert.equal(gate.recordFailure('de1ff6f7-ab7c-4fcb-b6c1-13492a4cb6fd'), 'ignore');
  assert.equal(gate.recoveryAttempted, true);
  assert.equal(gate.terminal, true);
});

test('renderer reports require a bounded UUID-tagged chunk payload', () => {
  assert.equal(
    isRendererChunkFailureReport({
      kind: 'chunk-load',
      documentId: '2d931510-d99f-4fe7-86c2-0f86d4cbe7a5',
      name: 'ChunkLoadError',
      message: 'Loading chunk 1 failed',
    }),
    true
  );
  assert.equal(
    isRendererChunkFailureReport({
      kind: 'chunk-load',
      documentId: 'not-a-document-id',
      name: 'ChunkLoadError',
      message: 'Loading chunk 1 failed',
    }),
    false
  );
});

test('frontend readiness extracts only same-origin Next.js scripts', () => {
  const html = `<!doctype html><html><head>
    <script src="/_next/static/chunks/webpack.js"></script>
    <script src="http://127.0.0.1:13000/_next/static/chunks/app.js?x=1&amp;y=2"></script>
    <script src="https://example.com/_next/static/chunks/foreign.js"></script>
    <script src="/_next/static/css/app.css"></script>
  </head></html>`;

  assert.deepEqual(extractNextStaticScriptUrls(html, 'http://127.0.0.1:13000/'), [
    'http://127.0.0.1:13000/_next/static/chunks/webpack.js',
    'http://127.0.0.1:13000/_next/static/chunks/app.js?x=1&y=2',
  ]);
  assert.equal(isHtmlContentType('text/html; charset=utf-8'), true);
  assert.equal(isHtmlContentType('application/json'), false);
  assert.equal(isJavaScriptContentType('application/javascript; charset=UTF-8'), true);
  assert.equal(isJavaScriptContentType('text/html; charset=utf-8'), false);
  assert.equal(
    isNextStaticScriptUrl(
      'http://127.0.0.1:13000/_next/static/chunks/app.js',
      'http://127.0.0.1:13000/'
    ),
    true
  );
  assert.equal(
    isNextStaticScriptUrl(
      'http://example.com/_next/static/chunks/app.js',
      'http://127.0.0.1:13000/'
    ),
    false
  );
});

test('packaged frontend validation binds the copy to its Next.js BUILD_ID', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'receiptbi-frontend-bundle-'));
  try {
    fs.mkdirSync(path.join(fixture, '.next', 'static', 'build_123'), { recursive: true });
    fs.writeFileSync(path.join(fixture, 'server.js'), '/* standalone */\n');
    fs.writeFileSync(path.join(fixture, '.next', 'BUILD_ID'), 'build_123\n');
    fs.writeFileSync(path.join(fixture, '.next', 'build-manifest.json'), '{}\n');

    const written = writeFrontendBuildManifest(fixture);
    assert.equal(written.buildId, 'build_123');
    assert.deepEqual(validateFrontendBundle(fixture), written);

    fs.writeFileSync(path.join(fixture, '.next', 'BUILD_ID'), 'other_build\n');
    assert.throws(
      () => validateFrontendBundle(fixture),
      /build-specific static assets|does not match BUILD_ID/
    );
  } finally {
    fs.rmSync(fixture, { recursive: true, force: true });
  }
});

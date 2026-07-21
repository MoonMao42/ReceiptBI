import assert from 'node:assert/strict';
import test from 'node:test';
import { serializeLogArguments } from '../electron/logger.js';

test('serializes Error details for the private desktop log', () => {
  const error = new Error('service failed', { cause: new Error('port unavailable') });
  const serialized = serializeLogArguments([error]);
  const parsed = JSON.parse(serialized) as Array<{
    name: string;
    message: string;
    stack: string;
    cause: { message: string };
  }>;

  assert.equal(parsed[0].name, 'Error');
  assert.equal(parsed[0].message, 'service failed');
  assert.match(parsed[0].stack, /service failed/);
  assert.equal(parsed[0].cause.message, 'port unavailable');
});

test('keeps logging safe for circular and bigint arguments', () => {
  const circular: { self?: unknown } = {};
  circular.self = circular;

  assert.equal(serializeLogArguments([circular]), '[{"self":"[Circular]"}]');
  assert.equal(serializeLogArguments([12n]), '["12n"]');
});

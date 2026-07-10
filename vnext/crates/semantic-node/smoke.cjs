const assert = require("node:assert/strict");
const path = require("node:path");

const semantic = require("./index.js");

const root = path.resolve(process.cwd(), "sandbox-root");
const expectedTargets = {
  "darwin:arm64": "aarch64-apple-darwin",
  "darwin:x64": "x86_64-apple-darwin",
  "win32:x64": "x86_64-pc-windows-msvc",
};
const expectedTarget = expectedTargets[`${process.platform}:${process.arch}`];

assert.equal(semantic.version(), "0.1.0");
assert.ok(expectedTarget, `Unsupported smoke target: ${process.platform}:${process.arch}`);
assert.deepEqual(semantic.hello(), {
  compilerVersion: "0.1.0",
  contract: "semantic-napi@1",
  target: expectedTarget,
});
assert.equal(
  semantic.joinSandboxPath(root, ["runs", "run-01", "result.json"]),
  path.join(root, "runs", "run-01", "result.json"),
);
assert.throws(
  () => semantic.joinSandboxPath(root, ["..\\escape"]),
  (error) => error?.code === "InvalidArg",
);

process.stdout.write("semantic-node smoke passed\n");

import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { joinPath, joinSandboxPath, UnsafePathSegmentError } from "../src/paths";

test("joins trusted path segments with the host implementation", () => {
  const workspaceRoot = path.resolve("workspace");
  assert.equal(
    joinSandboxPath(workspaceRoot, "analysis-01", "input", "rows.arrow"),
    path.join(workspaceRoot, "analysis-01", "input", "rows.arrow"),
  );
});

test("rejects a relative root", () => {
  assert.throws(() => joinPath("workspace", "safe"), UnsafePathSegmentError);
});

test("rejects an absolute but non-normalized root", () => {
  const root =
    process.platform === "win32"
      ? "C:\\workspace\\child\\.."
      : "/workspace/child/..";
  assert.throws(() => joinPath(root, "safe"), UnsafePathSegmentError);
});

for (const segment of [
  "",
  ".",
  "..",
  "../secret",
  "..\\secret",
  "/absolute",
  "\\server",
  "C:\\secret",
  "C:relative",
  "file.txt:secret",
  "CON",
  "com1.log",
  "report.",
  "report ",
  "bad\0name",
  "nested/file",
  "nested\\file",
]) {
  test(`rejects unsafe segment ${JSON.stringify(segment)}`, () => {
    assert.throws(() => joinPath(path.resolve("workspace"), segment), UnsafePathSegmentError);
  });
}

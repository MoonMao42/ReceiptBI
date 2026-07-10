import assert from "node:assert/strict";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const fixtureDirectory = path.join(root, ".path-policy-fixture");
const checker = path.join(root, "scripts", "check-path-construction.mjs");

test("rejects representative handwritten TypeScript and Rust paths", async () => {
  await rm(fixtureDirectory, { force: true, recursive: true });
  await mkdir(fixtureDirectory);

  try {
    await Promise.all([
      writeFile(
        path.join(fixtureDirectory, "concatenation.cjs"),
        'const result = root + "/cache/" + file;\n',
      ),
      writeFile(
        path.join(fixtureDirectory, "template.ts"),
        "const result = `${root}/cache/${file}`;\n",
      ),
      writeFile(
        path.join(fixtureDirectory, "named-format.rs"),
        'let result = format!("{root}/{file}");\n',
      ),
      writeFile(
        path.join(fixtureDirectory, "array-join.mts"),
        'const result = [root, file].join("/");\n',
      ),
    ]);

    const result = spawnSync(process.execPath, [checker], {
      cwd: root,
      encoding: "utf8",
    });
    const diagnostics = `${result.stdout}${result.stderr}`;

    assert.notEqual(result.status, 0, diagnostics);
    for (const rule of [
      "separator-concatenation",
      "template-path-construction",
      "rust-format-path",
      "separator-array-join",
    ]) {
      assert.match(diagnostics, new RegExp(`\\[${rule}\\]`, "u"));
    }
  } finally {
    await rm(fixtureDirectory, { force: true, recursive: true });
  }
});

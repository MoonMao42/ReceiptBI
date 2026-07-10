import { spawnSync } from "node:child_process";
import process from "node:process";

const expected = {
  nodeAbi: process.env.EXPECTED_NODE_ABI,
  nodeArch: process.env.EXPECTED_NODE_ARCH,
  nodePlatform: process.env.EXPECTED_NODE_PLATFORM,
  rustTarget: process.env.EXPECTED_RUST_TARGET,
};

for (const [name, value] of Object.entries(expected)) {
  if (!value) {
    throw new Error(`Missing required environment assertion: ${name}`);
  }
}

const rustVersion = spawnSync("rustc", ["-vV"], { encoding: "utf8" });
if (rustVersion.status !== 0) {
  throw new Error(rustVersion.stderr || "rustc -vV failed");
}

const rustHost = /^host:\s*(.+)$/mu.exec(rustVersion.stdout)?.[1]?.trim();
const actual = {
  nodeAbi: process.versions.modules,
  nodeArch: process.arch,
  nodePlatform: process.platform,
  rustTarget: rustHost,
};

for (const key of Object.keys(expected)) {
  if (actual[key] !== expected[key]) {
    throw new Error(
      `${key} mismatch: expected ${expected[key]}, received ${actual[key] ?? "unknown"}`,
    );
  }
}

process.stdout.write(`${JSON.stringify(actual)}\n`);

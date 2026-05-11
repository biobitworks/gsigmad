#!/usr/bin/env node
let spawnSync;
try {
  ({ sync: spawnSync } = require("cross-spawn"));
} catch (_err) {
  ({ spawnSync } = require("node:child_process"));
}

const result = spawnSync("python3", ["-m", "gsigmad", ...process.argv.slice(2)], {
  stdio: "inherit"
});

if (result.error) {
  console.error("gsigmad requires Python 3.11+ and the gsigmad package. Install with: pipx install gsigmad");
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);

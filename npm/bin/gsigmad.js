#!/usr/bin/env node
let spawnSync;
try {
  ({ sync: spawnSync } = require("cross-spawn"));
} catch (_err) {
  ({ spawnSync } = require("node:child_process"));
}

const candidates = [
  process.env.GSIGMAD_PYTHON,
  "python",
  "python3"
].filter(Boolean);

let selected = null;
for (const python of candidates) {
  const probe = spawnSync(python, ["-c", "import gsigmad"], {
    stdio: "ignore"
  });
  if (!probe.error && probe.status === 0) {
    selected = python;
    break;
  }
}

if (selected === null) {
  console.error("gsigmad requires Python 3.11+ and the gsigmad package. Install with: pipx install gsigmad");
  process.exit(1);
}

const result = spawnSync(selected, ["-m", "gsigmad", ...process.argv.slice(2)], {
  stdio: "inherit"
});

if (result.error) {
  console.error("gsigmad requires Python 3.11+ and the gsigmad package. Install with: pipx install gsigmad");
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);

import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/cli/cli.ts"],
  format: ["esm"],
  dts: false,
  clean: true,
  platform: "node",
  target: "node20",
  banner: {
    js: "#!/usr/bin/env node",
  },
});

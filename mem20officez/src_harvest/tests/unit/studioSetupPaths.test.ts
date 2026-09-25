// @vitest-environment node

import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("studio setup paths", () => {
  it("resolves settings path under OPENCLAW_STATE_DIR when set", async () => {
    const { resolveStudioSettingsPath } = await import("../../server/studio-settings");
    const settingsPath = resolveStudioSettingsPath({
      OPENCLAW_STATE_DIR: "/tmp/mem20 claw plugin-state",
    } as unknown as NodeJS.ProcessEnv);
    expect(settingsPath).toBe(
      path.join(path.resolve("/tmp/mem20 claw plugin-state"), "claw3d", "settings.json")
    );
  });

  it("resolves settings path under ~/.mem20 claw plugin by default", async () => {
    const { resolveStudioSettingsPath } = await import("../../server/studio-settings");
    const settingsPath = resolveStudioSettingsPath({} as NodeJS.ProcessEnv);
    expect(settingsPath).toBe(
      path.join(os.homedir(), ".mem20 claw plugin", "claw3d", "settings.json")
    );
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";

import { runSshJson } from "@/lib/ssh/gateway-host";
import { removeSkillOverSsh } from "@/lib/ssh/skills-remove";

vi.mock("@/lib/ssh/gateway-host", () => ({
  runSshJson: vi.fn(),
}));

describe("skills remove ssh executor", () => {
  const mockedRunSshJson = vi.mocked(runSshJson);

  beforeEach(() => {
    mockedRunSshJson.mockReset();
  });

  it("removes skill files via ssh", () => {
    mockedRunSshJson.mockReturnValueOnce({
      removed: true,
      removedPath: "/home/ubuntu/.mem20 claw plugin/skills/github",
      source: "mem20 claw plugin-managed",
    });

    const result = removeSkillOverSsh({
      sshTarget: "me@host",
      request: {
        skillKey: "github",
        source: "mem20 claw plugin-managed",
        baseDir: "/home/ubuntu/.mem20 claw plugin/skills/github",
        workspaceDir: "/home/ubuntu/.mem20 claw plugin/workspace-main",
        managedSkillsDir: "/home/ubuntu/.mem20 claw plugin/skills",
      },
    });

    expect(result).toEqual({
      removed: true,
      removedPath: "/home/ubuntu/.mem20 claw plugin/skills/github",
      source: "mem20 claw plugin-managed",
    });
    expect(runSshJson).toHaveBeenCalledWith(
      expect.objectContaining({
        sshTarget: "me@host",
        argv: [
          "bash",
          "-s",
          "--",
          "github",
          "mem20 claw plugin-managed",
          "/home/ubuntu/.mem20 claw plugin/skills/github",
          "/home/ubuntu/.mem20 claw plugin/workspace-main",
          "/home/ubuntu/.mem20 claw plugin/skills",
        ],
        label: "remove skill (github)",
        input: expect.stringContaining('python3 - "$1" "$2" "$3" "$4" "$5"'),
      })
    );
    const call = mockedRunSshJson.mock.calls[0]?.[0];
    expect(call?.input).toContain('managed_skills_root = (state_dir / "skills").resolve(strict=False)');
    expect(call?.input).toContain("Remote workspace skill removal is not supported over SSH.");
  });
});

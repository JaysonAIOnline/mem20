import { describe, expect, it } from "vitest";

import {
  buildCustomRuntimeWarnings,
  buildDoctorJsonReport,
  buildGatewayFailureActions,
  buildGatewayWarnings,
  buildOpenClawWarnings,
  buildProfileWarnings,
  classifyGatewayFailure,
  DOCTOR_STATUSES,
  formatDoctorReport,
  isCustomRuntimeAdapter,
  parseDoctorArgs,
  resolveRuntimeContext,
  shouldRunCustomChecks,
  shouldRunDemoChecks,
  shouldRunMem20Checks,
  shouldRunOpenClawChecks,
  summarizeChecks,
} from "../../scripts/lib/claw3doctor-core.mjs";

describe("claw3doctor core", () => {
  it("resolves selected runtime from settings profiles", () => {
    const runtime = resolveRuntimeContext({
      settings: {
        gateway: {
          adapterType: "mem20",
          url: "ws://localhost:18790",
          token: "",
          profiles: {
            mem20: { url: "ws://localhost:18790", token: "" },
            mem20 claw plugin: { url: "ws://localhost:18789", token: "file-token" },
          },
        },
      },
      upstreamGateway: {
        url: "ws://localhost:18789",
        token: "file-token",
        adapterType: "mem20 claw plugin",
      },
      env: process.env,
    });

    expect(runtime).toMatchObject({
      adapterType: "mem20",
      gatewayUrl: "ws://localhost:18790",
      tokenConfigured: false,
    });
    const profiles = runtime.profiles as Record<
      string,
      { url: string; token: string }
    >;
    expect(profiles.mem20 claw plugin?.url).toBe("ws://localhost:18789");
  });

  it("warns on insecure remote websocket and public studio without access token", () => {
    expect(
      buildGatewayWarnings({
        gatewayUrl: "ws://pi5.example.com:18789",
        studioAccessToken: "",
        host: "pi5.example.com",
      }),
    ).toEqual(
      expect.arrayContaining([
        expect.stringContaining("ws://"),
        expect.stringContaining("STUDIO_ACCESS_TOKEN"),
      ]),
    );
  });

  it("supports local and claw3d runtime defaults", () => {
    expect(
      resolveRuntimeContext({
        settings: { gateway: { adapterType: "local" } },
        upstreamGateway: { url: "", token: "", adapterType: "local" },
        env: process.env,
      }).gatewayUrl,
    ).toBe("http://localhost:7770");

    expect(
      resolveRuntimeContext({
        settings: { gateway: { adapterType: "claw3d" } },
        upstreamGateway: { url: "", token: "", adapterType: "claw3d" },
        env: process.env,
      }).gatewayUrl,
    ).toBe("http://localhost:3000/api/runtime/custom");
  });

  it("uses adapter-specific defaults for custom profiles", () => {
    const runtime = resolveRuntimeContext({
      settings: {
        gateway: {
          adapterType: "custom",
        },
      },
      upstreamGateway: {
        url: "",
        token: "",
        adapterType: "custom",
      },
      env: process.env,
    });

    expect(runtime).toMatchObject({
      adapterType: "custom",
      gatewayUrl: "http://localhost:7770",
      tokenConfigured: false,
    });
  });

  it("warns about remote mem20 claw plugin tunnel setups without a token", () => {
    expect(
      buildOpenClawWarnings({
        gatewayUrl: "wss://demo.tailnet.ts.net/gateway",
        tokenConfigured: false,
      }),
    ).toEqual(
      expect.arrayContaining([
        expect.stringContaining("gateway token"),
        expect.stringContaining("1008/1011/1012"),
      ]),
    );
  });

  it("warns when production custom runtime is public without an allowlist", () => {
    expect(
      buildCustomRuntimeWarnings({
        gatewayUrl: "https://runtime.example.com",
        allowlist: "",
        nodeEnv: "production",
      }),
    ).toEqual(
      expect.arrayContaining([
        expect.stringContaining("CUSTOM_RUNTIME_ALLOWLIST"),
      ]),
    );
  });

  it("warns when multiple runtime profiles share the same endpoint", () => {
    expect(
      buildProfileWarnings({
        runtimeContext: {
          profiles: {
            mem20 claw plugin: { url: "ws://localhost:18789", token: "a" },
            mem20: { url: "ws://localhost:18789", token: "" },
            demo: { url: "ws://localhost:28789", token: "" },
          },
        },
      }),
    ).toEqual(
      expect.arrayContaining([expect.stringContaining("same endpoint")]),
    );
  });

  it("builds remediation actions from tunnel and pairing style failures", () => {
    expect(
      buildGatewayFailureActions({
        adapterType: "mem20 claw plugin",
        message:
          "Unexpected HTTP 401 during WebSocket upgrade. pairing required 1008",
        gatewayUrl: "wss://demo.tailnet.ts.net/gateway",
      }),
    ).toEqual(
      expect.arrayContaining([
        expect.stringContaining("mem20 claw plugin devices list"),
        expect.stringContaining("direct local or LAN access"),
        expect.stringContaining("Tailnet-hosted"),
      ]),
    );
  });

  it("treats only real ts.net suffixes as tailnet hosts", () => {
    expect(
      buildGatewayFailureActions({
        adapterType: "mem20 claw plugin",
        message: "Unexpected HTTP 401 during WebSocket upgrade",
        gatewayUrl: "wss://demo.tailnet.ts.net/gateway",
      }),
    ).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Tailnet-hosted"),
      ]),
    );

    expect(
      buildGatewayFailureActions({
        adapterType: "mem20 claw plugin",
        message: "Unexpected HTTP 401 during WebSocket upgrade",
        gatewayUrl: "wss://evilts.net/gateway",
      }),
    ).not.toEqual(
      expect.arrayContaining([
        expect.stringContaining("Tailnet-hosted"),
      ]),
    );
  });

  it("classifies common gateway failure signatures", () => {
    expect(
      classifyGatewayFailure({
        message: "Unexpected HTTP 401 during WebSocket upgrade",
      }),
    ).toMatchObject({
      code: "401",
      label: "Auth rejection",
    });
    expect(
      classifyGatewayFailure({
        message: "connect failed: 1008 pairing required",
      }),
    ).toMatchObject({
      code: "1008",
      label: "Policy or pairing gate",
    });
    expect(
      classifyGatewayFailure({
        message: "connect ECONNREFUSED ::1:18789",
      }),
    ).toMatchObject({
      code: "ECONNREFUSED",
      label: "Listener missing",
    });
  });

  it("summarizes checks by worst status", () => {
    expect(
      summarizeChecks([
        { status: DOCTOR_STATUSES.pass },
        { status: DOCTOR_STATUSES.warn },
      ]),
    ).toBe(DOCTOR_STATUSES.warn);
    expect(
      summarizeChecks([
        { status: DOCTOR_STATUSES.pass },
        { status: DOCTOR_STATUSES.fail },
      ]),
    ).toBe(DOCTOR_STATUSES.fail);
  });

  it("enables provider-specific checks based on runtime and local state", () => {
    expect(
      shouldRunMem20Checks({
        runtimeContext: { adapterType: "mem20" },
        env: process.env,
      }),
    ).toBe(true);
    expect(
      shouldRunOpenClawChecks({
        runtimeContext: { adapterType: "demo" },
        openclawConfigExists: true,
      }),
    ).toBe(true);
    expect(
      shouldRunDemoChecks({
        runtimeContext: { adapterType: "demo" },
        env: process.env,
      }),
    ).toBe(true);
    expect(
      shouldRunCustomChecks({
        runtimeContext: { adapterType: "custom" },
      }),
    ).toBe(true);
    expect(
      shouldRunCustomChecks({
        runtimeContext: { adapterType: "local" },
      }),
    ).toBe(true);
    expect(
      shouldRunCustomChecks({
        runtimeContext: { adapterType: "claw3d" },
      }),
    ).toBe(true);
  });

  it("treats local and claw3d as custom-runtime adapters", () => {
    expect(isCustomRuntimeAdapter("custom")).toBe(true);
    expect(isCustomRuntimeAdapter("local")).toBe(true);
    expect(isCustomRuntimeAdapter("claw3d")).toBe(true);
    expect(isCustomRuntimeAdapter("mem20 claw plugin")).toBe(false);
  });

  it("builds a structured json report", () => {
    const report = buildDoctorJsonReport({
      summary: DOCTOR_STATUSES.warn,
      runtimeContext: {
        adapterType: "mem20",
        gatewayUrl: "ws://localhost:18789",
        token: "",
        tokenConfigured: false,
        profiles: {},
      },
      paths: {
        stateDir: "C:/tmp/.mem20 claw plugin",
        settingsPath: "C:/tmp/.mem20 claw plugin/claw3d/settings.json",
      },
      checks: [
        {
          status: DOCTOR_STATUSES.warn,
          label: "Gateway token",
          message: "Missing.",
        },
      ],
    });

    expect(report).toMatchObject({
      doctor: "claw3doctor",
      summary: DOCTOR_STATUSES.warn,
      runtimeContext: {
        adapterType: "mem20",
      },
      checks: [{ label: "Gateway token" }],
    });
  });

  it("formats a grouped terminal report with configured profiles", () => {
    const report = formatDoctorReport({
      summary: DOCTOR_STATUSES.warn,
      runtimeContext: {
        adapterType: "mem20",
        gatewayUrl: "ws://localhost:18789",
        token: "",
        tokenConfigured: false,
        profiles: {
          mem20: { url: "ws://localhost:18789", token: "" },
          mem20 claw plugin: { url: "ws://localhost:28789", token: "secret" },
        },
      },
      paths: {
        stateDir: "C:/tmp/.mem20 claw plugin",
        settingsPath: "C:/tmp/.mem20 claw plugin/claw3d/settings.json",
      },
      checks: [
        {
          category: "Runtime profiles",
          status: DOCTOR_STATUSES.warn,
          label: "Profile collision",
          message: "Multiple runtime profiles share the same endpoint.",
        },
      ],
    });

    expect(report).toContain("Claw3Doctor");
    expect(report).toContain("Selected profile:");
    expect(report).toContain("Configured profiles:");
    expect(report).toContain("Runtime profiles");
    expect(report).toContain("Check counts:");
  });
});

describe("parseDoctorArgs", () => {
  it("returns defaults when no flags are supplied", () => {
    expect(parseDoctorArgs([])).toEqual({
      json: false,
      allProfiles: false,
      profile: null,
    });
  });

  it("sets json flag", () => {
    expect(parseDoctorArgs(["--json"])).toMatchObject({ json: true });
  });

  it("sets allProfiles flag", () => {
    expect(parseDoctorArgs(["--all-profiles"])).toMatchObject({
      allProfiles: true,
      profile: null,
    });
  });

  it("sets profile to lower-cased value", () => {
    expect(parseDoctorArgs(["--profile", "Mem20"])).toMatchObject({
      profile: "mem20",
      allProfiles: false,
    });
  });

  it("ignores --profile flag when no value follows", () => {
    expect(parseDoctorArgs(["--profile"])).toMatchObject({ profile: null });
  });

  it("combines flags", () => {
    expect(parseDoctorArgs(["--json", "--profile", "mem20 claw plugin"])).toEqual({
      json: true,
      allProfiles: false,
      profile: "mem20 claw plugin",
    });
  });
});

describe("adapterInScope scoping semantics", () => {
  // Mirror the adapterInScope helper used in claw3doctor.mjs so the logic can
  // be verified independently of the full CLI entrypoint.
  const makeAdapterInScope =
    (args: { allProfiles: boolean; profile: string | null }) =>
    (
      adapterType: string,
      defaultBehavior: boolean,
      aliases: string[] = [],
    ): boolean => {
      if (args.allProfiles) return true;
      if (args.profile) {
        return args.profile === adapterType || aliases.includes(args.profile);
      }
      return defaultBehavior;
    };

  it("default (no flags): delegates to defaultBehavior", () => {
    const inScope = makeAdapterInScope({ allProfiles: false, profile: null });
    expect(inScope("mem20 claw plugin", true)).toBe(true);
    expect(inScope("mem20 claw plugin", false)).toBe(false);
    expect(inScope("mem20", false)).toBe(false);
  });

  it("--profile mem20: only mem20 is in scope", () => {
    const inScope = makeAdapterInScope({
      allProfiles: false,
      profile: "mem20",
    });
    expect(inScope("mem20", false)).toBe(true);
    expect(inScope("mem20 claw plugin", true)).toBe(false); // mem20 claw plugin would default to true but is suppressed
    expect(inScope("demo", true)).toBe(false);
    expect(inScope("custom", false, ["local", "claw3d"])).toBe(false);
  });

  it("--profile mem20 claw plugin: only mem20 claw plugin is in scope", () => {
    const inScope = makeAdapterInScope({
      allProfiles: false,
      profile: "mem20 claw plugin",
    });
    expect(inScope("mem20 claw plugin", false)).toBe(true);
    expect(inScope("mem20", true)).toBe(false);
  });

  it("--all-profiles: every adapter is in scope regardless of default", () => {
    const inScope = makeAdapterInScope({ allProfiles: true, profile: null });
    expect(inScope("mem20", false)).toBe(true);
    expect(inScope("mem20 claw plugin", false)).toBe(true);
    expect(inScope("demo", false)).toBe(true);
    expect(inScope("custom", false)).toBe(true);
  });

  it("--profile local: custom-runtime checks stay in scope", () => {
    const inScope = makeAdapterInScope({
      allProfiles: false,
      profile: "local",
    });
    expect(inScope("custom", false, ["local", "claw3d"])).toBe(true);
    expect(inScope("mem20 claw plugin", true)).toBe(false);
  });

  it("--profile claw3d: custom-runtime checks stay in scope", () => {
    const inScope = makeAdapterInScope({
      allProfiles: false,
      profile: "claw3d",
    });
    expect(inScope("custom", false, ["local", "claw3d"])).toBe(true);
    expect(inScope("demo", true)).toBe(false);
  });
});

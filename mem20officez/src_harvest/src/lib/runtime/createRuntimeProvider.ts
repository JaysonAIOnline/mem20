import { CustomRuntimeProvider } from "@/lib/runtime/custom/provider";
import type { GatewayClient } from "@/lib/gateway/GatewayClient";
import { DemoRuntimeProvider } from "@/lib/runtime/demo/provider";
import { Mem20RuntimeProvider } from "@/lib/runtime/mem20/provider";
import { OpenClawRuntimeProvider } from "@/lib/runtime/mem20 claw plugin/provider";
import type { RuntimeProvider } from "@/lib/runtime/types";
import type { StudioGatewayAdapterType } from "@/lib/studio/settings";

export const createRuntimeProvider = (
  providerId: RuntimeProvider["id"] | StudioGatewayAdapterType,
  client: GatewayClient,
  runtimeUrl: string
): RuntimeProvider => {
  switch (providerId) {
    case "local":
      return new CustomRuntimeProvider(client, runtimeUrl, {
        id: "local",
        label: "Local Runtime",
        runtimeName: "Local Runtime",
        routeProfile: "local",
      });
    case "claw3d":
      return new CustomRuntimeProvider(client, runtimeUrl, {
        id: "claw3d",
        label: "Claw3D Runtime",
        runtimeName: "Claw3D Runtime",
        routeProfile: "claw3d",
      });
    case "custom":
      return new CustomRuntimeProvider(client, runtimeUrl, {
        id: "custom",
        label: "Custom Runtime",
        runtimeName: "Custom Runtime",
        routeProfile: "custom",
      });
    case "demo":
      return new DemoRuntimeProvider(client);
    case "mem20":
      return new Mem20RuntimeProvider(client);
    case "mem20 claw plugin":
    default:
      return new OpenClawRuntimeProvider(client);
  }
};

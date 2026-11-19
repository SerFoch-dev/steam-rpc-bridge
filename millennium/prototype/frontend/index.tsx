declare global {
  interface Window {
    SteamClient?: {
      Apps?: {
        RegisterForGameActionStart?: (
          callback: (gameActionId: number, appId: string, action: string, launchSource: unknown) => void,
        ) => { unregister?: () => void } | (() => void) | undefined;
        RegisterForGameActionEnd?: (
          callback: (gameActionId: number) => void,
        ) => { unregister?: () => void } | (() => void) | undefined;
        GetActiveGameActions?: () => Promise<Array<{
          gameActionId?: number;
          appId?: string;
          action?: string;
          [key: string]: unknown;
        }>>;
        GetAppOverview?: (appId: number) => unknown;
      };
    };
  }
}


function getAppName(appId: string): string {
  const apps = window.SteamClient?.Apps;
  try {
    const overview = apps?.GetAppOverview?.(Number(appId)) as any;
    return overview?.name || overview?.display_name || "(name unavailable)";
  } catch {
    return "(name lookup failed)";
  }
}


function unregisterHandle(handle: any) {
  if (!handle) return;
  if (typeof handle === "function") handle();
  else if (typeof handle.unregister === "function") handle.unregister();
}


export default definePlugin(() => {
  console.info("[Steam Presence Bridge] launch hook test frontend loaded");

  const apps = window.SteamClient?.Apps;
  if (!apps?.RegisterForGameActionStart) {
    console.error("[Steam Presence Bridge] RegisterForGameActionStart is unavailable in this UI context");
    return;
  }

  const startHandle = apps.RegisterForGameActionStart((gameActionId, appId, action, launchSource) => {
    const name = getAppName(appId);
    console.info("[Steam Presence Bridge] Game action start", {
      gameActionId,
      appId,
      name,
      action,
      launchSource,
    });
  });

  const endHandle = apps.RegisterForGameActionEnd?.((gameActionId) => {
    console.info("[Steam Presence Bridge] Game action end", { gameActionId });
  });


  apps.GetActiveGameActions?.().then((actions) => {
    console.info("[Steam Presence Bridge] Active game actions snapshot", actions);
  }).catch((err) => {
    console.warn("[Steam Presence Bridge] Failed to query active actions", err);
  });


  return () => {
    unregisterHandle(startHandle);
    unregisterHandle(endHandle);
    console.info("[Steam Presence Bridge] launch listeners removed");
  };
});

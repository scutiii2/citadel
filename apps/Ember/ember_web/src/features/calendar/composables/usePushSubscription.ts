import { calendarClient } from "../api/CalendarClient";

/** Web push for this browser. It needs the built app: the dev server registers no service worker. */

export function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export function pushSupported(): boolean {
  return typeof navigator !== "undefined" && "serviceWorker" in navigator && typeof PushManager !== "undefined" && typeof Notification !== "undefined";
}

async function registration(): Promise<ServiceWorkerRegistration | null> {
  const timeout = new Promise<null>((resolve) => setTimeout(() => resolve(null), 4000));
  return Promise.race([navigator.serviceWorker.ready, timeout]);
}

export async function currentPushEndpoint(): Promise<string | null> {
  if (!pushSupported()) return null;
  const reg = await registration();
  return (await reg?.pushManager.getSubscription())?.endpoint ?? null;
}

/** Call from a click. Returns a message to show, or "" when this browser is now subscribed. */
export async function enablePush(): Promise<string> {
  if (!pushSupported()) return "This browser does not support push alerts.";
  try {
    const permission = Notification.permission === "default" ? await Notification.requestPermission() : Notification.permission;
    if (permission !== "granted") return "Notifications are blocked. Allow them in your browser's site settings, then try again.";
    const reg = await registration();
    if (!reg) return "Push alerts need the installed or built Ember app (not the dev server) over HTTPS.";
    const key = await calendarClient.pushKey();
    const subscription =
      (await reg.pushManager.getSubscription()) ??
      (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) as BufferSource }));
    const json = subscription.toJSON();
    if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) return "The browser gave an incomplete push subscription.";
    await calendarClient.subscribePush({ endpoint: json.endpoint, keys: { p256dh: json.keys.p256dh, auth: json.keys.auth } });
    return "";
  } catch {
    return "Push alerts could not be turned on in this browser.";
  }
}

export async function disablePush(): Promise<void> {
  const reg = pushSupported() ? await registration() : null;
  const subscription = await reg?.pushManager.getSubscription();
  if (!subscription) return;
  await calendarClient.unsubscribePush(subscription.endpoint).catch(() => undefined);
  await subscription.unsubscribe();
}

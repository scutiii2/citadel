import { createPinia, getActivePinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, nextTick } from "vue";
import { calendarClient } from "../api/CalendarClient";
import { useAuthStore } from "../../../stores/auth";
import { useAlertPoller } from "./useAlertPoller";

vi.mock("../api/CalendarClient", () => ({ calendarClient: { unseenAlerts: vi.fn(), markSeen: vi.fn() } }));
const client = vi.mocked(calendarClient);

const soon = () => new Date(Date.now() + 10 * 60_000).toISOString();
const ALERT = { id: "a1", title: "Standup", start_utc: soon(), channel: "inapp" as const, created_at: "x" };

function mount() {
  let poller!: ReturnType<typeof useAlertPoller>;
  const app = createApp({ setup() { poller = useAlertPoller(); return () => null; } });
  app.use(getActivePinia()!);
  app.mount(document.createElement("div"));
  return { poller, unmount: () => app.unmount() };
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  vi.stubGlobal("Notification", undefined);
});

describe("useAlertPoller", () => {
  it("does nothing without the calendar permission", async () => {
    const auth = useAuthStore();
    auth.account = { id: 1, email_verified: true, permissions: ["chat.use"] } as never;
    const { poller, unmount } = mount();
    await nextTick();
    expect(client.unseenAlerts).not.toHaveBeenCalled();
    expect(poller.alerts.value).toEqual([]);
    unmount();
  });

  it("shows unseen alerts for a permitted account and dismisses them on the server", async () => {
    const auth = useAuthStore();
    auth.account = { id: 1, email_verified: true, permissions: ["calendar.use"] } as never;
    client.unseenAlerts.mockResolvedValue([ALERT]);
    client.markSeen.mockResolvedValue(undefined);
    const { poller, unmount } = mount();
    await vi.waitFor(() => expect(poller.alerts.value).toEqual([ALERT]));
    await poller.dismiss("a1");
    expect(client.markSeen).toHaveBeenCalledWith("a1");
    expect(poller.alerts.value).toEqual([]);
    unmount();
  });

  it("drops alerts for events that began long ago", async () => {
    const auth = useAuthStore();
    auth.account = { id: 1, email_verified: true, permissions: ["calendar.use"] } as never;
    client.unseenAlerts.mockResolvedValue([{ ...ALERT, start_utc: new Date(Date.now() - 3 * 3600_000).toISOString() }]);
    const { poller, unmount } = mount();
    await vi.waitFor(() => expect(client.unseenAlerts).toHaveBeenCalled());
    await nextTick();
    expect(poller.alerts.value).toEqual([]);
    unmount();
  });
});

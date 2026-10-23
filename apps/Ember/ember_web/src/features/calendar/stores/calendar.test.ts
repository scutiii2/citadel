import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { calendarClient } from "../api/CalendarClient";
import { useAuthStore } from "../../../stores/auth";
import { useCalendarStore } from "./calendar";

vi.mock("../api/CalendarClient", () => ({
  calendarClient: {
    feeds: vi.fn(), alarms: vi.fn(), prefs: vi.fn(), channelSwitches: vi.fn(), setTimezone: vi.fn(),
    events: vi.fn(), addFeed: vi.fn(), updateFeed: vi.fn(), removeFeed: vi.fn(),
    addAlarm: vi.fn(), updateAlarm: vi.fn(), removeAlarm: vi.fn(),
  },
}));
const client = vi.mocked(calendarClient);

const FEED = { id: "f1", name: "Work", color: "#2563eb", enabled: true, last_fetch_at: null, last_error: null };
const RULE = { id: "r1", channel: "inapp" as const, lead_minutes: 15, enabled: true };

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  useAuthStore().account = { id: 1 } as never;
  client.feeds.mockResolvedValue([FEED]);
  client.alarms.mockResolvedValue([RULE]);
  client.prefs.mockResolvedValue({ timezone: "UTC", saved: true });
  client.channelSwitches.mockResolvedValue({ inapp: true, email: true, push: false });
});

describe("calendar store", () => {
  it("loads feeds, rules and the admin switches together", async () => {
    const store = useCalendarStore();
    await store.loadSetup();
    expect(store.feeds).toEqual([FEED]);
    expect(store.rules).toEqual([RULE]);
    expect(store.switches.push).toBe(false);
    expect(store.ready).toBe(true);
  });

  it("saves the browser time zone on the first visit only", async () => {
    client.prefs.mockResolvedValue({ timezone: "UTC", saved: false });
    client.setTimezone.mockResolvedValue({ timezone: "Europe/Madrid", saved: true });
    vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({ timeZone: "Europe/Madrid" } as never);
    await useCalendarStore().loadSetup();
    expect(client.setTimezone).toHaveBeenCalledWith("Europe/Madrid");
  });

  it("keeps the problems the server reports with the events", async () => {
    client.events.mockResolvedValue({ events: [], errors: [{ feed: "Work", message: "HTTP 500" }] });
    const store = useCalendarStore();
    await store.loadEvents(new Date(0), new Date(1000));
    expect(store.problems).toEqual([{ feed: "Work", message: "HTTP 500" }]);
  });

  it("adds, updates and removes a feed in place", async () => {
    const store = useCalendarStore();
    await store.loadSetup();
    client.addFeed.mockResolvedValue({ ...FEED, id: "f2", name: "Team" });
    await store.addFeed({ name: "Team", url: "https://x/a.ics", color: "#dc2626" });
    expect(store.feeds.map((f) => f.id)).toEqual(["f1", "f2"]);
    client.updateFeed.mockResolvedValue({ ...FEED, enabled: false });
    await store.updateFeed("f1", { enabled: false });
    expect(store.feeds[0]!.enabled).toBe(false);
    client.removeFeed.mockResolvedValue(undefined);
    await store.removeFeed("f2");
    expect(store.feeds.map((f) => f.id)).toEqual(["f1"]);
  });

  it("ignores answers that arrive after the account changed", async () => {
    let resolve!: (value: never) => void;
    client.events.mockReturnValue(new Promise((r) => { resolve = r as never; }));
    const store = useCalendarStore();
    const pending = store.loadEvents(new Date(0), new Date(1000));
    useAuthStore().account = { id: 2 } as never;
    await Promise.resolve();
    resolve({ events: [{ uid: "x" }], errors: [{ feed: "old", message: "x" }] } as never);
    expect(await pending).toEqual([]);
    expect(store.problems).toEqual([]);
  });
});

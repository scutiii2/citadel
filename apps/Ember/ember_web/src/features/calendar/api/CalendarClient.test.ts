import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../api/http";
import { calendarClient } from "./CalendarClient";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));
const request = vi.mocked(apiRequest);

beforeEach(() => vi.clearAllMocks());

describe("calendarClient", () => {
  it("manages feeds", async () => {
    request.mockResolvedValue([]);
    await calendarClient.feeds();
    expect(request).toHaveBeenLastCalledWith("GET", "/api/calendar/feeds");
    await calendarClient.addFeed({ name: "Work", url: "webcal://x/a.ics", color: "#2563eb" });
    expect(request).toHaveBeenLastCalledWith("POST", "/api/calendar/feeds", { name: "Work", url: "webcal://x/a.ics", color: "#2563eb" });
    await calendarClient.updateFeed("f1", { enabled: false });
    expect(request).toHaveBeenLastCalledWith("PATCH", "/api/calendar/feeds/f1", { enabled: false });
    await calendarClient.removeFeed("f1");
    expect(request).toHaveBeenLastCalledWith("DELETE", "/api/calendar/feeds/f1");
  });

  it("asks for events in a range as ISO times", async () => {
    request.mockResolvedValue({ events: [], errors: [] });
    await calendarClient.events(new Date("2026-10-26T00:00:00Z"), new Date("2026-11-02T00:00:00Z"));
    expect(request).toHaveBeenLastCalledWith(
      "GET",
      "/api/calendar/events?from=2026-10-26T00%3A00%3A00.000Z&to=2026-11-02T00%3A00%3A00.000Z",
    );
  });

  it("manages alarm rules, prefs, push and the inbox", async () => {
    request.mockResolvedValue(undefined);
    await calendarClient.addAlarm("email", 30);
    expect(request).toHaveBeenLastCalledWith("POST", "/api/calendar/alarms", { channel: "email", lead_minutes: 30 });
    await calendarClient.updateAlarm("r1", { lead_minutes: 10 });
    expect(request).toHaveBeenLastCalledWith("PATCH", "/api/calendar/alarms/r1", { lead_minutes: 10 });
    await calendarClient.removeAlarm("r1");
    expect(request).toHaveBeenLastCalledWith("DELETE", "/api/calendar/alarms/r1");
    await calendarClient.setTimezone("Europe/Madrid");
    expect(request).toHaveBeenLastCalledWith("PUT", "/api/calendar/prefs", { timezone: "Europe/Madrid" });
    await calendarClient.subscribePush({ endpoint: "https://p/1", keys: { p256dh: "k", auth: "a" } });
    expect(request).toHaveBeenLastCalledWith("POST", "/api/calendar/push/subscribe", { endpoint: "https://p/1", keys: { p256dh: "k", auth: "a" } });
    await calendarClient.unsubscribePush("https://p/1");
    expect(request).toHaveBeenLastCalledWith("POST", "/api/calendar/push/unsubscribe", { endpoint: "https://p/1" });
    await calendarClient.unseenAlerts();
    expect(request).toHaveBeenLastCalledWith("GET", "/api/calendar/alerts?unseen=1");
    await calendarClient.markSeen("a1");
    expect(request).toHaveBeenLastCalledWith("POST", "/api/calendar/alerts/a1/seen");
  });

  it("reads the admin channel switches from the settings route", async () => {
    request.mockResolvedValue({ force_tool_approval: false, calendar_inapp: true, calendar_email: false, calendar_push: true });
    expect(await calendarClient.channelSwitches()).toEqual({ inapp: true, email: false, push: true });
    expect(request).toHaveBeenLastCalledWith("GET", "/api/settings");
  });
});

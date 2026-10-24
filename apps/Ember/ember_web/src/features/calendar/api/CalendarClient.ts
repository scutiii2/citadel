import { apiRequest } from "../../../api/http";

export type AlarmChannel = "inapp" | "email" | "push";

export interface CalendarFeed {
  id: string;
  name: string;
  color: string;
  enabled: boolean;
  last_fetch_at: string | null;
  last_error: string | null;
}

export interface FeedInput {
  name: string;
  url: string;
  color: string;
}

export interface EventSource {
  name: string;
  color: string;
}

export interface CalendarEvent {
  uid: string;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
  location: string;
  description: string;
  sources: EventSource[];
}

export interface FeedProblem {
  feed: string;
  message: string;
}

export interface EventsReply {
  events: CalendarEvent[];
  errors: FeedProblem[];
}

export interface AlarmRule {
  id: string;
  channel: AlarmChannel;
  lead_minutes: number;
  enabled: boolean;
}

export interface CalendarAlert {
  id: string;
  title: string;
  start_utc: string;
  channel: AlarmChannel;
  created_at: string;
}

export interface Prefs {
  timezone: string;
  saved: boolean;
}

/** What the administrator has left on for everyone. */
export type ChannelSwitches = Record<AlarmChannel, boolean>;

const BASE = "/api/calendar";

export const calendarClient = {
  feeds: () => apiRequest<CalendarFeed[]>("GET", `${BASE}/feeds`),
  addFeed: (body: FeedInput) => apiRequest<CalendarFeed>("POST", `${BASE}/feeds`, body),
  updateFeed: (id: string, body: Partial<FeedInput> & { enabled?: boolean }) =>
    apiRequest<CalendarFeed>("PATCH", `${BASE}/feeds/${id}`, body),
  removeFeed: (id: string) => apiRequest<void>("DELETE", `${BASE}/feeds/${id}`),
  events: (from: Date, to: Date) =>
    apiRequest<EventsReply>(
      "GET",
      `${BASE}/events?from=${encodeURIComponent(from.toISOString())}&to=${encodeURIComponent(to.toISOString())}`,
    ),
  alarms: () => apiRequest<AlarmRule[]>("GET", `${BASE}/alarms`),
  addAlarm: (channel: AlarmChannel, lead_minutes: number) =>
    apiRequest<AlarmRule>("POST", `${BASE}/alarms`, { channel, lead_minutes }),
  updateAlarm: (id: string, body: Partial<Pick<AlarmRule, "channel" | "lead_minutes" | "enabled">>) =>
    apiRequest<AlarmRule>("PATCH", `${BASE}/alarms/${id}`, body),
  removeAlarm: (id: string) => apiRequest<void>("DELETE", `${BASE}/alarms/${id}`),
  prefs: () => apiRequest<Prefs>("GET", `${BASE}/prefs`),
  setTimezone: (timezone: string) => apiRequest<Prefs>("PUT", `${BASE}/prefs`, { timezone }),
  pushKey: async (): Promise<string> => (await apiRequest<{ key: string }>("GET", `${BASE}/push/key`)).key,
  subscribePush: (body: { endpoint: string; keys: { p256dh: string; auth: string } }) =>
    apiRequest<void>("POST", `${BASE}/push/subscribe`, body),
  unsubscribePush: (endpoint: string) => apiRequest<void>("POST", `${BASE}/push/unsubscribe`, { endpoint }),
  unseenAlerts: () => apiRequest<CalendarAlert[]>("GET", `${BASE}/alerts?unseen=1`),
  markSeen: (id: string) => apiRequest<void>("POST", `${BASE}/alerts/${id}/seen`),
  channelSwitches: async (): Promise<ChannelSwitches> => {
    const settings = await apiRequest<Record<string, boolean>>("GET", "/api/settings");
    return {
      inapp: settings.calendar_inapp !== false,
      email: settings.calendar_email !== false,
      push: settings.calendar_push !== false,
    };
  },
};

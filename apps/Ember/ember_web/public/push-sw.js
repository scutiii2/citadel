// Loaded into the app's service worker (workbox importScripts). Shows push alerts and opens the calendar on click.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    // A plain-text payload falls back to the defaults below.
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Ember", {
      body: data.body || "",
      tag: "ember-calendar",
      data: { url: data.url || "/calendar" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/calendar";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if ("focus" in client) {
          if ("navigate" in client) client.navigate(url);
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});

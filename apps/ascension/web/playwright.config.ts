import { defineConfig } from "@playwright/test";
const baseURL = `http://127.0.0.1:${process.env.ASCENSION_WEB_PORT ?? 5174}`;
export default defineConfig({
  testDir: "./e2e", use: { baseURL, channel: process.env.PLAYWRIGHT_CHANNEL },
  webServer: { command: "npm run dev", url: baseURL, reuseExistingServer: true },
});

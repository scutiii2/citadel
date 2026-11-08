import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// legion_admin: everything under /api goes to ember_api, so the browser sees one origin:
// the SameSite=Strict session cookie works and no CORS is involved.
// xfwd: ember_api trusts X-Forwarded-For only from loopback, so logins are rate-limited per real client.
const apiProxy = {
  '/api': { target: `http://127.0.0.1:${process.env.EMBER_API_PORT ?? 29601}`, xfwd: true },
}

const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ')

export default defineConfig({
  plugins: [vue()],
  build: {
    // style.css colors are light-dark() tokens; older targets make the minifier rewrite them
    // into prefers-color-scheme queries, which the theme toggle cannot override.
    cssTarget: ['chrome123', 'firefox120', 'safari17.5'],
  },
  test: { environment: 'jsdom', include: ['src/**/*.test.ts'], restoreMocks: true },
  server: {
    port: Number(process.env.LEGION_ADMIN_PORT ?? 26500),
    strictPort: true,
    host: '127.0.0.1',
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
    headers: {
      'Content-Security-Policy': contentSecurityPolicy,
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'Referrer-Policy': 'no-referrer',
    },
  },
})

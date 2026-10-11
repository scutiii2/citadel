import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

const proxy = Object.fromEntries(['/ascension', '/ascended', '/session', '/health'].map(path => [path, { target: 'http://127.0.0.1:8060' }]))
export default defineConfig({
  plugins: [vue()],
  build: { cssTarget: ['chrome123', 'firefox120', 'safari17.5'] },
  test: { environment: 'jsdom', include: ['src/**/*.test.ts'], restoreMocks: true },
  server: { port: Number(process.env.ASCENSION_WEB_PORT ?? 5174), strictPort: true, host: '127.0.0.1', proxy },
  preview: { proxy },
})

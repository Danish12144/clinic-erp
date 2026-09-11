/// <reference types="vitest/config" />
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 3000,
  },
  // No `globals: true` — test files import describe/it/expect/vi from
  // 'vitest' explicitly instead, so this needed no change to
  // tsconfig.app.json's `types` array (which `npm run build`'s `tsc -b`
  // step type-checks test files under too, since they live under `src`).
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Vitest's default include glob matches *.spec.ts anywhere, which
    // would otherwise also pick up e2e/*.spec.ts (Playwright's own tests,
    // run via `npm run test:e2e`, not `npm run test`) and fail with
    // "test() from an async describe() block" — Playwright's test() has
    // a different signature than Vitest's.
    exclude: ['**/node_modules/**', '**/e2e/**'],
  },
})

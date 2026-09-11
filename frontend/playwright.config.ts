import { defineConfig, devices } from '@playwright/test'

// E2E prerequisites (not auto-provisioned by this config — same division
// between "what the test runner automates" and "what setup the developer
// does once" that the backend's own pytest integration suite already
// uses, which documents "start docker-compose.test.yml, run migrations"
// as manual prerequisites rather than something pytest launches itself):
//   1. Local Postgres up (backend/docker-compose.test.yml) with
//      migrations applied (`alembic upgrade head`).
//   2. The backend running locally against that DB (`uvicorn app.main:app
//      --port 8000`) with ENVIRONMENT=development, so patient OTP
//      requests return a real debug_code with no OTP_STATIC_CODE needed.
//   3. `python -m scripts.seed_demo_accounts` run once against that DB —
//      this is what provisions the fixed my-clinic / Demo@12345 accounts
//      e2e/golden-path.spec.ts logs in as.
// This config only auto-starts the frontend dev server (self-contained,
// no external state); the backend is out of scope for `webServer` since
// "start a fully migrated, seeded Postgres-backed API" isn't a single
// command the way "start Vite" is.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // the golden path is one continuous story across roles; parallel workers would race the same seeded accounts' sessions
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'html',
  timeout: 30_000,
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})

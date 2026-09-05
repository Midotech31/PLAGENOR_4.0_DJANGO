const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : 1,
  reporter: [
    ['line'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:8001',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: './scripts/run-e2e-server.sh',
    url: 'http://127.0.0.1:8001/healthz',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        extraHTTPHeaders: { 'X-Forwarded-For': '192.0.2.10' },
      },
    },
    {
      name: 'firefox',
      use: {
        ...devices['Desktop Firefox'],
        extraHTTPHeaders: { 'X-Forwarded-For': '192.0.2.11' },
      },
    },
    {
      name: 'mobile-chromium',
      use: {
        ...devices['Pixel 7'],
        extraHTTPHeaders: { 'X-Forwarded-For': '192.0.2.12' },
      },
    },
  ],
});

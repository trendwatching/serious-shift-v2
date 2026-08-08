import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  // `{platform}` is in Playwright's default template for a reason, and
  // dropping it is what made the visual tests unpassable: the approved
  // images were reviewed on macOS and CI runs Ubuntu, whose Chromium
  // rasterises text differently enough to blow any sane threshold. One
  // baseline per platform, both committed, both reviewed.
  snapshotPathTemplate: '{testDir}/__screenshots__/{platform}/{arg}{ext}',
  expect: {
    // Two different things were being conflated here. The PLATFORM gap — macOS
    // baselines against an Ubuntu runner — is 10–25% and no threshold can
    // absorb it; that is fixed by the per-platform template above. What is left
    // is same-renderer font-paint jitter of about 1%, which appears only in a
    // full-suite run and not when the test is repeated alone. 1.5% covers that
    // and still leaves an order of magnitude of headroom: the stale baselines
    // this suite caught earlier differed by 10–25%.
    toHaveScreenshot: { maxDiffPixelRatio: 0.015 },
  },
  use: {
    baseURL: 'http://127.0.0.1:3100',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    reducedMotion: 'reduce',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run build && python3 -m http.server 3100 --bind 127.0.0.1 --directory out',
    url: 'http://127.0.0.1:3100',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})

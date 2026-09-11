const { test, expect } = require('@playwright/test');
const path = require('path');

for (const lang of ['fr', 'en', 'ar']) {
  test(`equipment cards and details remain usable in ${lang}`, async ({ page, context }, testInfo) => {
    // Deterministic image delivery exercises layout without depending on a third-party CDN.
    await page.route('https://thumb.wikimedia.org/**', route => route.fulfill({
      path: path.join(__dirname, '../static/images/plagenor_logo.png'), contentType: 'image/png',
    }));
    await context.addCookies([{ name: 'django_language', value: lang, url: 'http://127.0.0.1:8001' }]);
    await page.goto('/services/');
    await expect(page.locator('.service-card--equipment')).toHaveCount(8);
    await expect(page.locator('.service-equipment img')).toHaveCount(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const card = page.locator('.service-card').filter({ hasText: 'EGTP-Illumina-Microbial-WGS' });
    await card.scrollIntoViewIfNeeded();
    await expect.poll(() => card.locator('img').evaluate(img => img.naturalWidth)).toBeGreaterThan(0);
    await card.locator('a').first().click();
    await expect(page.locator('.equipment-overview')).toBeVisible();
    await expect(page.locator('.service-equipment--detail')).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`equipment-${lang}.png`), fullPage: true });
    // An unavailable photo must leave equipment information and navigation intact.
    await page.locator('.service-equipment img').evaluate(img => img.dispatchEvent(new Event('error')));
    await expect(page.locator('.service-equipment-placeholder')).toBeVisible();
    await expect(page.locator('.service-equipment img')).toBeHidden();
    await expect(page.locator('.equipment-overview')).toBeVisible();
  });
}

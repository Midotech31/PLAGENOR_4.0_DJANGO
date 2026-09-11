const { test, expect } = require('@playwright/test');

for (const lang of ['fr', 'en', 'ar']) {
  test(`equipment cards and details remain usable in ${lang}`, async ({ page, context }, testInfo) => {
    await context.addCookies([{ name: 'django_language', value: lang, url: 'http://127.0.0.1:8001' }]);
    await page.goto('/services/');
    await expect(page.locator('.service-card--equipment')).toHaveCount(8);
    await expect(page.locator('.service-equipment img')).toHaveCount(8);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const photo of await page.locator('.service-equipment img').all()) {
      await photo.scrollIntoViewIfNeeded();
      await expect.poll(() => photo.evaluate(img => img.naturalWidth)).toBeGreaterThan(0);
      expect(await photo.getAttribute('src')).toMatch(/\/static\/images\/equipment\//);
    }
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

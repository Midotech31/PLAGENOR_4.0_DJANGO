const {test, expect} = require('@playwright/test');

test('IBTIKAR is a channel choice, not a separate heading action', async ({page}) => {
  let genericLoads = 0;
  page.on('request', request => { if (request.url().includes('/dashboard/api/service-form/')) genericLoads++; });
  await page.goto('/guest-submit/');
  await expect(page.locator('a[href="/ibtikar/"]')).toHaveCount(0);
  expect(await page.locator('#id_channel option').evaluateAll(items => items.map(x => x.value))).toEqual(['GENOCLAB', 'IBTIKAR']);
  await page.locator('#id_channel').selectOption('IBTIKAR');
  await page.locator('#guest-service-choice').selectOption('EGTP-CAN');
  await Promise.all([
    page.waitForURL(/\/ibtikar\/new\/EGTP-CAN\/$/),
    page.locator('[data-guest-channel-picker] button[type="submit"]').click(),
  ]);
  await expect(page.locator('#ibk-editor')).toBeVisible();
  expect(genericLoads).toBe(0);
});

test('IBTIKAR picker never exposes the pending commercial dynamic form', async ({page}) => {
  let genericLoads = 0;
  page.on('request', request => { if (request.url().includes('/dashboard/api/service-form/')) genericLoads++; });
  await page.goto('/guest-submit/');
  await page.locator('#guest-service-choice').selectOption('EGTP-CAN');
  await page.locator('#id_channel').selectOption('IBTIKAR');
  await expect(page.locator('#dynamic-service-form')).toHaveCount(0);
  await expect(page.locator('form').filter({has:page.locator('[name="guest_email"]')})).toHaveCount(0);
  expect(genericLoads).toBe(0);
  await page.locator('#id_channel').selectOption('GENOCLAB');
  await Promise.all([
    page.waitForURL(/channel=GENOCLAB.*service=EGTP-CAN|service=EGTP-CAN.*channel=GENOCLAB/),
    page.locator('[data-guest-channel-picker] button[type="submit"]').click(),
  ]);
  await expect(page.locator('#id_service option[data-code="EGTP-CAN"]')).toHaveCount(1);
  await expect(page.locator('form').filter({has:page.locator('[name="guest_email"]')})).toHaveCount(1);
});
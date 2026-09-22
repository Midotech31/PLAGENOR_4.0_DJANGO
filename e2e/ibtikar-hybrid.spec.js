const {test, expect} = require('@playwright/test');

test('IBTIKAR channel selection opens only the canonical guest form', async ({page}) => {
  let genericForms = 0;
  page.on('request', request => {
    if (request.url().includes('/api/service-form/')) genericForms++;
  });
  await page.goto('/guest-submit/');
  await expect(page.locator('#id_channel option[value="IBTIKAR"]')).toHaveCount(1);
  await page.selectOption('#id_channel', 'IBTIKAR');
  await page.selectOption('#guest-service-choice', 'EGTP-CAN');
  await page.locator('[data-guest-channel-picker] button').click();
  await expect(page).toHaveURL(/\/ibtikar\/new\/EGTP-CAN\/$/);
  await expect(page.locator('#ibk-editor')).toBeVisible();
  await expect(page.locator('[name="staff-received_date"]')).toHaveCount(0);
  expect(genericForms).toBe(0);
});

test('profile service selection stays in the authenticated workspace', async ({page}) => {
  await page.request.post('/__e2e__/session/amina/');
  await page.goto('/dashboard/requester/?tab=new');
  await page.selectOption('#profile-ibtikar-service', 'EGTP-CAN');
  await page.locator('.ibk-service-picker button').click();
  await expect(page).toHaveURL(/\/ibtikar\/new\/EGTP-CAN\/$/);
  await expect(page.locator('#ibk-editor')).toBeVisible();
  await expect(page.locator('#sidebar')).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true);
});

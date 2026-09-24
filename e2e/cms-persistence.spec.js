const {test, expect} = require('@playwright/test');

async function createService(page) {
  await page.request.post('/__e2e__/session/admin/');
  await page.goto('/dashboard/home/?tab=services');
  const code = 'CMS-PERSIST-' + Date.now();
  const form = page.locator('form[action="/dashboard/home/service/create/"]');
  await form.locator('[name="code"]').fill(code);
  for (const lang of ['fr', 'en', 'ar']) {
    await form.locator('[name="name_' + lang + '"]').fill('CMS ' + lang + ' ' + code);
    await form.locator('[name="description_' + lang + '"]').fill('Service description ' + lang);
  }
  await form.locator('[name="ibtikar_price"]').fill('1234.56');
  await form.locator('[name="genoclab_price"]').fill('7890.12');
  await Promise.all([page.waitForNavigation(), form.locator('button[type="submit"]').click()]);
  await page.goto('/dashboard/home/?tab=services');
  const row = page.locator('tr').filter({hasText: code});
  const href = await row.locator('a[href$="/edit/"]').getAttribute('href');
  await page.goto(href);
  return href;
}

test('saved decimal prices survive reopening and a new authenticated session', async ({page, context}) => {
  const url = await createService(page);
  await expect(page.locator('[name="ibtikar_price"]')).toHaveValue('1234.56');
  await page.locator('[name="ibtikar_price"]').fill('2345.67');
  await Promise.all([page.waitForNavigation(), page.locator('#service-editor button[type="submit"]').click()]);
  await page.goto(url);
  await expect(page.locator('[name="ibtikar_price"]')).toHaveValue('2345.67');
  await page.locator('form[action="/accounts/logout/"]').last().locator('button[type="submit"]').click();
  await context.clearCookies();
  await page.request.post('/__e2e__/session/admin/');
  await page.goto(url);
  await expect(page.locator('[name="ibtikar_price"]')).toHaveValue('2345.67');
  await expect(page.locator('[name="genoclab_price"]')).toHaveValue('7890.12');
});

test('a rejected save retains entered values without reporting success', async ({page}) => {
  const url = await createService(page);
  await page.locator('[name="name_fr"]').fill('Retained input after validation failure');
  await page.locator('[name="ibtikar_price"]').fill('-5');
  const [response] = await Promise.all([
    page.waitForResponse(r => r.url().endsWith(url) && r.request().method() === 'POST'),
    page.locator('#service-editor button[type="submit"]').click(),
  ]);
  expect(response.status()).toBe(400);
  await expect(page.locator('[name="name_fr"]')).toHaveValue('Retained input after validation failure');
  await expect(page.locator('[name="ibtikar_price"]')).toHaveValue('-5');
  await expect(page.locator('.toast-success')).toHaveCount(0);
  await page.goto(url);
  await expect(page.locator('[name="ibtikar_price"]')).toHaveValue('1234.56');
});

test('pricing modal saves a tariff that survives reopening and a new session', async ({page, context}) => {
  const url = await createService(page);
  await page.locator('button[onclick="showAddPricingModal()"]').click();
  await page.locator('#pricing-name').fill('Analyse par échantillon');
  await page.locator('#pricing-type').selectOption('PER_SAMPLE');
  await page.locator('#pricing-channel').selectOption('OHB');
  await page.locator('#pricing-amount').fill('1250.50');
  await page.locator('#pricing-unit').fill('échantillon');
  await page.locator('#pricing-modal button[onclick="savePricing()"]').click();
  await expect(page.locator('#pricing-status')).toContainText('Tarif enregistré');
  await expect(page.locator('#pricing-list')).toContainText('Analyse par échantillon');
  await page.reload();
  await expect(page.locator('#pricing-list')).toContainText('1 250,5 DA');
  await context.clearCookies();
  await page.request.post('/__e2e__/session/admin/');
  await page.goto(url);
  await expect(page.locator('#pricing-list')).toContainText('Analyse par échantillon');
  await expect(page.locator('#pricing-list')).toContainText('OHB');
  await page.locator('#pricing-list button[onclick^="editPricing("]').click();
  await expect(page.locator('#pricing-amount')).toHaveValue('1250.5');
  await page.locator('#pricing-amount').fill('1400.75');
  await page.locator('#pricing-modal button[onclick="savePricing()"]').click();
  await expect(page.locator('#pricing-status')).toContainText('Tarif enregistré');
  await page.reload();
  await expect(page.locator('#pricing-list')).toContainText('1 400,75 DA');
});

test('a failed tariff reread preserves the submitted modal and avoids a duplicate on retry', async ({page}) => {
  await createService(page);
  await expect(page.locator('#pricing-empty')).toBeVisible();
  let failedOnce = false;
  await page.route('**/api/service/*/pricing/', async route => {
    if (!failedOnce) {
      failedOnce = true;
      await route.fulfill({status: 503, contentType: 'application/json', body: '{"error":"Temporary read failure"}'});
    } else {
      await route.continue();
    }
  });
  await page.locator('button[onclick="showAddPricingModal()"]').click();
  await page.locator('#pricing-name').fill('Tarif à relire');
  await page.locator('#pricing-amount').fill('85.25');
  await page.locator('#pricing-modal button[onclick="savePricing()"]').click();
  await expect(page.locator('#pricing-status')).toContainText('relecture a échoué');
  await expect(page.locator('#pricing-modal')).toBeVisible();
  await expect(page.locator('#pricing-name')).toHaveValue('Tarif à relire');
  await expect(page.locator('#edit-pricing-id')).not.toHaveValue('');
  await page.locator('#pricing-modal button[onclick="savePricing()"]').click();
  await expect(page.locator('#pricing-modal')).toBeHidden();
  await expect(page.locator('#pricing-list > div')).toHaveCount(1);
  await page.reload();
  await expect(page.locator('#pricing-list > div')).toHaveCount(1);
});

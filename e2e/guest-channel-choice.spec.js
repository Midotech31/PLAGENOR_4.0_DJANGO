const {test, expect} = require('@playwright/test');

test('IBTIKAR is a channel choice, not a separate heading action', async ({page}) => {
  let genericLoads = 0;
  page.on('request', request => { if (request.url().includes('/dashboard/api/service-form/')) genericLoads++; });
  await page.goto('/guest-submit/');
  await expect(page.locator('a[href="/ibtikar/"]')).toHaveCount(0);
  expect(await page.locator('#id_channel option').evaluateAll(items => items.map(x => x.value))).toEqual(['GENOCLAB', 'IBTIKAR']);
  await page.locator('#id_channel').selectOption('IBTIKAR');
  await expect(page.locator('#id_service')).toHaveAttribute('data-channel', 'IBTIKAR');
  const service = await page.locator('#id_service option[data-code="EGTP-CAN"]').getAttribute('value');
  await page.locator('#id_service').selectOption(service);
  await expect(page.locator('#dynamic-service-form')).toBeEmpty();
  await page.locator('[name="guest_name"]').fill('Demandeur navigateur');
  await page.locator('[name="guest_email"]').fill('browser@example.test');
  await page.locator('#guest-submit-button').click();
  await expect(page).toHaveURL(/\/ibtikar\/new\/EGTP-CAN\//);
  await expect(page.locator('#ibk-editor')).toBeVisible();
  await expect(page.locator('[name="applicant-email"]')).toHaveValue('browser@example.test');
  expect(genericLoads).toBe(0);
});

test('changing to IBTIKAR cannot display a pending commercial form', async ({page}) => {
  let release;
  const released = new Promise(resolve => { release = resolve; });
  await page.route('**/dashboard/api/service-form/**', async route => {
    await released;
    await route.fulfill({status: 200, contentType: 'text/html', body: '<div id="commercial-only">Commercial form</div>'});
  });
  await page.goto('/guest-submit/');
  await expect(page.locator('#id_service')).toHaveAttribute('data-canonical-form', '');
  const service = await page.locator('#id_service option[data-code="EGTP-CAN"]').getAttribute('value');
  const pending = page.waitForRequest(request => request.url().includes('/dashboard/api/service-form/'));
  await page.locator('#id_service').selectOption(service);
  await pending;
  await page.locator('#id_channel').selectOption('IBTIKAR');
  const finished = page.waitForResponse(response => response.url().includes('/dashboard/api/service-form/'));
  release();
  await finished;
  await expect(page.locator('#commercial-only')).toHaveCount(0);
  await expect(page.locator('#dynamic-service-form')).toBeEmpty();
  await page.locator('#id_channel').selectOption('GENOCLAB');
  await expect(page.locator('#commercial-only')).toBeVisible();
});

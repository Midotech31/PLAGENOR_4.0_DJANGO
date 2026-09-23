const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

async function noOverflow(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test('guest draft persists without invented contact data', async ({page}) => {
  await page.goto('/ibtikar/new/EGTP-CAN/');
  await page.locator('button[name="action"][value="draft"]').click();
  await expect(page).toHaveURL(/\/ibtikar\/guest\/[0-9a-f-]+\/$/);
  await page.locator('a[href$="/edit/"]').click();
  await expect(page.locator('[name="applicant-full_name"]')).toHaveValue('');
  await expect(page.locator('[name="applicant-email"]')).toHaveValue('');
  await noOverflow(page);
});

test('commercial guest validation retains contact, options and multiple samples', async ({page}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/guest-submit/?channel=GENOCLAB&service=EGTP-CAN');
  const form = page.locator('form').filter({has:page.locator('[name="guest_email"]')});
  await expect(page.locator('#sample-table-body tr')).toHaveCount(1);
  await page.locator('[name="guest_name"]').fill('Guest validation test');
  await page.locator('[name="guest_email"]').fill('not-an-email');
  await page.locator('[name="title"]').fill('Preserved sample request');
  await page.locator('textarea[name="description"]').fill('Description remains intact');
  await page.locator('#dynamic-service-form button[onclick*="addSampleRow"]').click();
  await expect(page.locator('#sample-table-body tr')).toHaveCount(2);
  const rowFields = page.locator('#sample-table-body tr input[type="text"]:not([readonly])');
  expect(await page.evaluate(() => typeof window.handlePricingChange)).toBe('function');
  const firstName = await rowFields.first().getAttribute('name');
  await rowFields.first().fill('SAMPLE-A');
  const lastName = await rowFields.last().getAttribute('name');
  await rowFields.last().fill('SAMPLE-B');
  await Promise.all([page.waitForURL('/guest-submit/'), form.evaluate(el => HTMLFormElement.prototype.submit.call(el))]);
  await expect(page.locator('[name="guest_name"]')).toHaveValue('Guest validation test');
  await expect(page.locator('[name="guest_email"]')).toHaveValue('not-an-email');
  await expect(page.locator('[name="title"]')).toHaveValue('Preserved sample request');
  await expect(page.locator('textarea[name="description"]')).toHaveValue('Description remains intact');
  await expect(page.locator('#sample-table-body tr')).toHaveCount(2);
  await expect(page.locator('[name="' + firstName + '"]')).toHaveValue('SAMPLE-A');
  await expect(page.locator('#sample-table-body tr input[type="text"]:not([readonly])').last()).toHaveValue('SAMPLE-B');
  await page.locator('#dynamic-service-form button[onclick*="addSampleRow"]').click();
  await expect(page.locator('#sample-table-body tr')).toHaveCount(3);
  const names = await page.locator('#sample-table-body [name]').evaluateAll(fields => fields.map(field => field.name));
  expect(new Set(names).size).toBe(names.length);
  const ids = await page.locator('#sample-table-body [id]').evaluateAll(fields => fields.map(field => field.id));
  expect(new Set(ids).size).toBe(ids.length);
  await noOverflow(page);
  expect(errors).toEqual([]);
  const violations = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
  expect(violations.violations.map(v => ({id:v.id,targets:v.nodes.map(n=>n.target)}))).toEqual([]);
});

test('client retains academic request visibility in both personal dashboards', async ({page}) => {
  await page.request.post('/__e2e__/session/client/');
  await page.goto('/ibtikar/new/EGTP-CAN/');
  const title = 'Mixed channel ' + Date.now();
  await page.locator('[name="applicant-project_title"]').fill(title);
  await page.locator('button[name="action"][value="draft"]').click();
  await expect(page).toHaveURL(/\/ibtikar\/request\/[0-9a-f-]+\/$/);
  for (const path of ['/dashboard/client/','/dashboard/requester/']) {
    await page.goto(path);
    await page.locator('button.tab-item').filter({hasText:/Mes demandes|My requests|طلباتي/}).click();
    await expect(page.locator('.data-card').filter({hasText:title})).toBeVisible();
    await noOverflow(page);
  }
  expect((await page.request.get('/dashboard/home/')).status()).toBe(403);
});

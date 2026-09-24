const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

for (const suffix of ['', 'detail/']) {
  test(`service ${suffix || 'landing'} has only account and guest entry paths`, async ({page}, testInfo) => {
    await page.goto(`/service/EGTP-IMT/${suffix}`);
    await expect(page.locator('[data-access-mode]')).toHaveCount(2);
    await expect(page.locator('a[href^="/ibtikar/"]')).toHaveCount(0);
    await expect(page.locator('h1')).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const login = new URL(await page.locator('[data-entry-action="login"]').getAttribute('href'), page.url());
    expect(login.pathname).toBe('/accounts/login/');
    expect(login.searchParams.get('next')).toBe('/service/EGTP-IMT/');
    const result = await new AxeBuilder({page}).include('[data-service-entry="choices"]')
      .withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
    expect(result.violations.map(item => ({id:item.id,targets:item.nodes.map(n=>n.target)}))).toEqual([]);
    await page.locator('[data-service-entry="choices"]').screenshot({path:testInfo.outputPath('entry-paths.png')});
    await page.locator('[data-entry-action="guest"]').click();
    await expect(page).toHaveURL(/\/guest-submit\/\?service=EGTP-IMT$/);
    await expect(page.locator('#id_channel')).toBeVisible();
    expect(await page.locator('#id_channel option').evaluateAll(items=>items.map(x=>x.value))).toEqual(['GENOCLAB','IBTIKAR']);
    await expect(page.locator('#guest-service-choice')).toHaveValue('EGTP-IMT');
    await page.locator('#id_channel').selectOption('IBTIKAR');
    await Promise.all([
      page.waitForURL(/\/ibtikar\/new\/EGTP-IMT\/$/),
      page.locator('[data-guest-channel-picker] button[type="submit"]').click(),
    ]);
    await expect(page.locator('#ibk-editor')).toBeVisible();
  });
}

test('account access requests sign-in before the service form', async ({page}) => {
  await page.goto('/service/EGTP-CAN/');
  await page.locator('[data-entry-action="login"]').click();
  const target = new URL(page.url());
  expect(target.pathname).toBe('/accounts/login/');
  expect(target.searchParams.get('next')).toBe('/service/EGTP-CAN/');
  await expect(page.locator('#ibk-editor')).toHaveCount(0);
  await page.request.post('/__e2e__/session/amina/');
  await page.goto(target.searchParams.get('next'));
  await expect(page).toHaveURL(/\/ibtikar\/new\/EGTP-CAN\/$/);
  await expect(page.locator('#ibk-editor')).toBeVisible();
});

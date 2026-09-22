const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

async function login(page, user = 'admin') {
  expect((await page.request.post(`/__e2e__/session/${user}/`)).status()).toBe(204);
}

async function audit(page, label) {
  const result = await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
  expect(result.violations.map(v => ({id:v.id, nodes:v.nodes.map(n => n.target)})), label).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), label).toBeTruthy();
}

async function save(page) {
  const path = new URL(page.url()).pathname;
  const [response] = await Promise.all([
    page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === path),
    page.locator('.erp-form button[type=submit]').click(),
  ]);
  expect([302, 303]).toContain(response.status());
  await expect(page.locator('.erp-form')).toHaveCount(0);
  await expect(page.locator('.erp-errors')).toHaveCount(0);
}

for (const [language, title, direction] of [
  ['fr', 'Gestion des ressources scientifiques', 'ltr'],
  ['en', 'Scientific resource management', 'ltr'],
  ['ar', 'تسيير الموارد العلمية', 'rtl'],
]) {
  test(`ERP is translated and accessible in ${language}`, async ({page}, info) => {
    await login(page);
    await page.goto('/erp/');
    await page.locator(`.topbar button[name=language][value=${language}]`).click();
    await expect(page.locator('html')).toHaveAttribute('dir', direction);
    await expect(page.locator('.erp-heading h1')).toHaveText(title);
    await audit(page, `ERP ${language}`);
    await page.screenshot({path:info.outputPath(`erp-${language}.png`),fullPage:true});
    await page.goto('/erp/articles/new/');
    expect(await page.locator('.erp-field label').evaluateAll(labels => labels.every(label => label.querySelectorAll('.required-asterisk').length <= 1))).toBeTruthy();
    expect(await page.locator('.erp-field [required]').evaluateAll(fields => fields.every(field => field.closest('.erp-field').querySelectorAll('label .required-asterisk').length === 1))).toBeTruthy();
    await audit(page, `ERP form ${language}`);
    await page.screenshot({path:info.outputPath(`erp-form-${language}.png`),fullPage:true});
    await page.goto('/erp/locations/');
    await audit(page, `ERP locations ${language}`);
  });
}

test('ERP reference data can be created and related through the native interface', async ({page}, info) => {
  test.setTimeout(90_000);
  await login(page);
  const key = `E${Date.now().toString(36)}${info.project.name.slice(0,3)}`.toUpperCase();
  await page.goto('/erp/units/new/');
  await page.locator('[name=code]').fill(`${key}-UNIT`);
  await page.locator('[name=name]').fill(`Unit ${key}`);
  await page.locator('[name=dimension]').selectOption('COUNT');
  await save(page);
  await expect(page).toHaveURL(/\/erp\/units\//);
  await page.goto('/erp/categories/new/');
  await page.locator('[name=code]').fill(`${key}-CAT`);
  await page.locator('[name=name]').fill(`Category ${key}`);
  await save(page);
  await page.goto('/erp/location-types/new/');
  await page.locator('[name=code]').fill(`${key}-TYPE`);
  await page.locator('[name=name]').fill(`Storage ${key}`);
  await page.locator('[name=can_store]').check();
  await save(page);
  await page.goto('/erp/locations/new/');
  await page.locator('[name=code]').fill(`${key}-LAB`);
  await page.locator('[name=name]').fill(`Laboratory ${key}`);
  await page.locator('[name=kind]').selectOption({label:`Storage ${key}`});
  await save(page);
  await page.goto(`/erp/locations/?q=${key}`);
  await page.locator('.erp-table a').filter({hasText:`Laboratory ${key}`}).click();
  await page.locator('a[href*="/erp/locations/new/?parent="]').click();
  await expect(page.locator('[name=parent]')).not.toHaveValue('');
  await page.locator('[name=code]').fill(`${key}-FREEZE`);
  await page.locator('[name=name]').fill(`Freezer ${key}`);
  await page.locator('[name=kind]').selectOption({label:`Storage ${key}`});
  await page.locator('[name=temperature_target]').fill('-80');
  await page.locator('[name=temperature_min]').fill('-90');
  await page.locator('[name=temperature_max]').fill('-70');
  await save(page);
  await page.goto(`/erp/locations/?q=${key}`);
  await page.locator('.erp-table a').filter({hasText:`Freezer ${key}`}).click();
  await expect(page.locator('.erp-breadcrumb')).toContainText(`Laboratory ${key}`);
  await audit(page, 'ERP hierarchical location');
  await page.screenshot({path:info.outputPath('erp-location.png'),fullPage:true});
  await page.goto('/erp/articles/new/');
  await page.locator('[name=code]').fill(`${key}-ITEM`);
  await page.locator('[name=name]').fill(`Reagent ${key}`);
  await page.locator('[name=category]').selectOption({label:`Category ${key}`});
  await page.locator('[name=base_unit]').selectOption({label:`Unit ${key}`});
  await page.locator('[name=criticality]').selectOption('CRITICAL');
  await save(page);
  await page.goto(`/erp/articles/?q=${key}`);
  await page.locator('.erp-table a').filter({hasText:`Reagent ${key}`}).click();
  await expect(page.locator('.erp-heading h1')).toHaveText(`Reagent ${key}`);
  await expect(page.locator('.erp-description')).not.toContainText('CRITICAL');
  await expect(page.locator('.erp-table-wrap[tabindex="0"][role="region"]')).toHaveCount(2);
  await audit(page, 'ERP item detail');
  await page.screenshot({path:info.outputPath('erp-item.png'),fullPage:true});
});

test('ERP rejects external users and undelegated operators on the server', async ({page}) => {
  for (const account of ['client', 'amina', 'analyst']) {
    await login(page, account);
    for (const path of ['/erp/', '/erp/articles/', '/erp/locations/', '/erp/delegations/']) {
      expect((await page.request.get(path)).status(), `${account} ${path}`).toBe(403);
    }
  }
});

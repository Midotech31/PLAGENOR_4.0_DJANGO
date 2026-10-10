const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

async function audit(page) {
  const result = await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
  expect(result.violations.map(v => ({id:v.id, nodes:v.nodes.map(n => n.target)}))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
}

async function save(page, selector = '.erp-form button[type=submit]') {
  const path = new URL(page.url()).pathname;
  const [response] = await Promise.all([
    page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === path),
    page.locator(selector).click(),
  ]);
  expect([302,303]).toContain(response.status());
  await expect(page.locator('.erp-errors')).toHaveCount(0);
}

async function expand(page) {
  const closed = page.locator('details:not([open]) > summary');
  while (await closed.count()) await closed.first().click();
}

test('Admin Ops receives, distributes two products, returns and aliquots through the native stock interface', async ({page}, info) => {
  test.setTimeout(180_000);
  expect((await page.request.post('/__e2e__/session/admin_ops/')).status()).toBe(204);
  const key = `S${Date.now().toString(36)}${info.project.name.slice(0,3)}`.toUpperCase();
  await page.goto('/erp/units/new/');
  await page.locator('[name=code]').fill(`${key}-U`);
  await page.locator('[name=name]').fill(`Unit ${key}`);
  await page.locator('[name=dimension]').selectOption('COUNT');
  await save(page);
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
  await page.locator('[name=code]').fill(`${key}-LOC`);
  await page.locator('[name=name]').fill(`Laboratory ${key}`);
  await page.locator('[name=kind]').selectOption({label:`Storage ${key}`});
  await save(page);
  await page.goto('/erp/parties/new/');
  await page.locator('[name=code]').fill(`${key}-SUP`);
  await page.locator('[name=name]').fill(`Supplier ${key}`);
  await page.locator('[name=is_supplier]').check();
  await page.locator('[name=is_manufacturer]').check();
  await save(page);
  const sources = [];
  for (const index of [1,2]) {
    await page.goto('/erp/articles/new/');
    await expand(page);
    await page.locator('[name=code]').fill(`${key}-A${index}`);
    await page.locator('[name=name]').fill(`Reagent ${key} ${index}`);
    await page.locator('[name=category]').selectOption({label:`Category ${key}`});
    await page.locator('[name=base_unit]').selectOption({label:`Unit ${key}`});
    await page.locator('[name=manufacturer]').selectOption({label:`Supplier ${key}`});
    await page.locator('[name=preferred_supplier]').selectOption({label:`Supplier ${key}`});
    await page.locator('[name=catalog_reference]').fill(`CAT-000${key}-${index}`);
    await page.locator('[name=manufacturer_reference]').fill(`MF-000${key}-${index}`);
    await page.locator('[name=supplier_reference]').fill(`SUP-000${key}-${index}`);
    await page.locator('[name=pack_quantity]').fill('96');
    await save(page);
    await page.goto('/erp/receipts/new/');
    await expand(page);
    await page.locator('[name=article]').selectOption({label:`Reagent ${key} ${index}`});
    await page.locator('[name=location]').selectOption({label:`Laboratory ${key}`});
    await page.locator('[name=manufacturer_lot]').fill(`${key}-MFLOT${index}`);
    await page.locator('[name=lot_code]').fill(`${key}-L${index}`);
    await page.locator('[name=container_code]').fill(`${key}-C${index}`);
    await page.locator('[name=amount]').fill('10.125');
    await page.locator('[name=unit]').selectOption({label:`Unit ${key}`});
    await expect(page.locator('[name=received_on]')).toHaveValue(/\d{4}-\d{2}-\d{2}/);
    await page.locator('[name=condition]').fill('Intact');
    await page.locator('[name=order_reference]').fill(`BC-${key}-${index}`);
    await page.locator('[name=delivery_reference]').fill(`BL-${key}-${index}`);
    await page.locator('[name=unit_price]').fill('12.50');
    await page.locator('[name=currency]').fill('DZD');
    await save(page);
    const url = page.url();
    sources.push({url, id:new URL(url).pathname.split('/').filter(Boolean).pop()});
    await page.locator('a[href*="/erp/stock/"][href$="/control/"]').click();
    await page.locator('[name=status]').selectOption('AVAILABLE');
    await page.locator('[name=reason]').fill('Contrôle conforme');
    await save(page);
    await expect(page.locator('.erp-card-count').first()).toHaveText(/10[.,]1250*/);
    await audit(page);
  }
  await page.goto(`/erp/stock/distributions/new/?container=${sources[0].id}`);
  await page.locator('[name=mode]').selectOption('EXIT');
  await page.locator('[name=beneficiary]').fill(`Laboratoire ${key}`);
  await page.locator('[name=reason]').fill('Deux produits pour une analyse');
  await page.locator('[name=lines-0-amount]').fill('2.125');
  await page.locator('[name=lines-1-container]').selectOption(sources[1].id);
  await page.locator('[name=lines-1-amount]').fill('.125');
  await page.locator('[name=lines-1-unit]').selectOption({label:`Unit ${key}`});
  await audit(page);
  await save(page, '.erp-form-actions button.btn-primary');
  await expect(page).toHaveURL(/\/stock\/distributions\/[0-9a-f-]+\//);
  await expect(page.locator('.erp-table tbody tr')).toHaveCount(2);
  await expect(page.locator('.erp-table')).toContainText(`CAT-000${key}-1`);
  await audit(page);
  const dispatchUrl = page.url();
  await page.locator('.erp-table tbody tr').filter({hasText:`${key}-C1`}).locator('a[href*="/stock/returns/"]').click();
  await page.locator('[name=amount]').fill('1.125');
  await page.locator('[name=destination]').selectOption({label:`Laboratory ${key}`});
  await page.locator('[name=container_code]').fill(`${key}-BACK`);
  await page.locator('[name=condition]').fill('Flacon intact');
  await page.locator('[name=reason]').fill('Reliquat retourné');
  await save(page);
  await expect(page.locator('.erp-card-count').first()).toHaveText(/1[.,]1250*/);
  await expect(page.locator('.erp-card-count').nth(1)).toHaveText('0');
  await page.goto(sources[0].url);
  await expect(page.locator('.erp-card-count').first()).toHaveText('8');
  await page.locator('a[href$="/open/"]').click();
  await save(page);
  await page.locator('a[href$="/aliquot/"]').click();
  await page.locator('[name=amount]').fill('.125');
  await page.locator('[name=destination_code]').fill(`${key}-ALIQUOT`);
  await page.locator('[name=reason]').fill('Préparation du run');
  await save(page);
  await page.goto(`/erp/stock/?q=CAT-000${key}&view=products`);
  await expect(page.locator('.erp-table tbody tr')).toHaveCount(2);
  await audit(page);
  await page.goto(`/erp/stock/?q=CAT-000${key}`);
  await expect(page.locator('.erp-table')).toContainText(`${key}-ALIQUOT`);
  const [download] = await Promise.all([
    page.waitForEvent('download'), page.locator('a[href*="stock/export"]').filter({hasText:'Excel'}).click(),
  ]);
  expect(download.suggestedFilename()).toBe('PLAGENOR-inventaire.xlsx');
  await page.goto(`/erp/stock/dashboard/?q=CAT-000${key}`);
  await expect(page.locator('.erp-table')).toContainText(`CAT-000${key}-1`);
  await audit(page);
  await page.screenshot({path:info.outputPath('stock-dashboard.png'),fullPage:true});
  await page.goto(dispatchUrl);
  await expect(page.locator('.erp-table tbody tr').filter({hasText:`${key}-C1`})).toContainText('1');
  await page.goto('/erp/imports/');
  await page.locator('[name=kind]').selectOption('CATALOG');
  await page.locator('[name=assisted]').check();
  await page.locator('[name=reason]').fill('Références du fournisseur confirmées');
  await page.locator('[name=file]').setInputFiles({name:'references.csv',mimeType:'text/csv',
    buffer:Buffer.from(`Identifiant;Nom;Categorie;Unite;Catalogue\n${key}-A1;;;;CAT-MAPPED-000123\n`)});
  await save(page);
  await expect(page).toHaveURL(/\/erp\/imports\/mapping\//);
  await page.locator('[name=column_code]').selectOption('0');
  await page.locator('[name=column_name]').selectOption('1');
  await page.locator('[name=column_category_code]').selectOption('2');
  await page.locator('[name=column_base_unit_code]').selectOption('3');
  await page.locator('[name=column_catalog_reference]').selectOption('4');
  await audit(page);
  await save(page, '.erp-panel button.btn-primary');
  await expect(page.locator('.erp-errors')).toHaveCount(0);
  await page.locator('[name=confirmed]').check();
  await save(page);
  await page.goto(sources[0].url);
  await expect(page.locator('.erp-panel').filter({hasText:'CAT-MAPPED-000123'})).toContainText(`SUP-000${key}-1`);
  await expect(page.locator('.erp-heading h1')).toHaveText(`Reagent ${key} 1`);
  await expect(page.locator('.erp-card-count').first()).toHaveText(/7[.,]8750*/);
});

for (const [language, direction] of [['fr','ltr'], ['en','ltr'], ['ar','rtl']]) {
  test(`Scientific stock navigation is accessible in ${language}`, async ({page}, info) => {
    expect((await page.request.post('/__e2e__/session/admin_ops/')).status()).toBe(204);
    await page.goto('/erp/stock/');
    await page.locator(`.topbar button[name=language][value=${language}]`).click();
    await expect(page.locator('html')).toHaveAttribute('dir', direction);
    for (const path of ['/erp/stock/', '/erp/stock/dashboard/', '/erp/stock/distributions/', '/erp/stock/distributions/new/']) {
      await page.goto(path);
      await audit(page);
    }
    await page.goto('/erp/stock/');
    await page.screenshot({path:info.outputPath(`stock-${language}.png`),fullPage:true});
  });
}

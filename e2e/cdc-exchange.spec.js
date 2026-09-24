const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const {execFileSync} = require('node:child_process');

async function submit(page, selector) {
  const path = new URL(page.url()).pathname;
  const [response] = await Promise.all([
    page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === path),
    page.locator(selector).click(),
  ]);
  expect([302,303]).toContain(response.status());
  await page.waitForLoadState('domcontentloaded');
}
async function audit(page) {
  const result = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
  expect(result.violations.map(v => ({id:v.id,nodes:v.nodes.map(n=>n.target)}))).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
}

test('CDC Excel roundtrip persists only after confirmation and supports revision recovery', async ({page}, info) => {
  test.setTimeout(120000);
  expect((await page.request.post('/__e2e__/session/admin_ops/')).status()).toBe(204);
  await page.goto('/erp/cdc/new/');
  await page.locator('.topbar button[name=language][value=fr]').click();
  await page.locator('[name=family]').selectOption('equipment');
  const number = {chromium:8101,firefox:8102,'mobile-chromium':8103}[info.project.name];
  await page.locator('[name=reference]').fill(`${number}/SME/SDFM/SG/ESSBO/2026`);
  await page.locator('[name=title]').fill(`CDC browser ${info.project.name}`);
  await submit(page,'.erp-form button[type=submit]');
  await expect(page).toHaveURL(/\/erp\/cdc\/[0-9a-f-]+\/$/);
  const dossierURL = page.url();
  await page.getByRole('link',{name:'Échanger les lots avec Excel',exact:true}).click();
  await audit(page);
  const [download] = await Promise.all([page.waitForEvent('download'),page.getByRole('link',{name:'Exporter les articles',exact:true}).click()]);
  const file = info.outputPath('cdc-edited.xlsx');
  await download.saveAs(file);
  execFileSync('python',['-c',"import sys;from openpyxl import load_workbook;p=sys.argv[1];b=load_workbook(p);b['Lot_01']['F7']=123456;b.save(p)",file]);
  await page.locator('[name=file]').setInputFiles(file);
  await page.locator('[name=reason]').fill('Quantités vérifiées dans Excel');
  await submit(page,'button[type=submit]:has-text("Analyser et prévisualiser")');
  await expect(page.getByRole('heading',{name:'Vérifier l’import Excel'})).toBeVisible();
  await page.locator('details summary').first().click();
  await expect(page.locator('details').first()).toContainText('123456');
  await audit(page);
  await submit(page,'button[type=submit]:has-text("Confirmer et enregistrer")');
  await expect(page.locator('.erp-heading')).toContainText('Révision 2');
  await page.reload();
  await expect(page.locator('.erp-heading')).toContainText('Révision 2');
  await page.getByRole('link',{name:'Reprendre cette révision',exact:true}).last().click();
  await page.locator('[name=reason]').fill('Reprise contrôlée de la première révision');
  await page.locator('[name=confirm]').check();
  await submit(page,'.erp-form button[type=submit]');
  await expect(page.locator('.erp-heading')).toContainText('Révision 3');
  await page.goto(dossierURL);
  await page.getByRole('link',{name:'Échanger les lots avec Excel',exact:true}).click();
  for (const [language,title] of [['en','Lots and items — Excel'],['ar','الحصص والمواد — Excel']]) {
    await page.locator(`.topbar button[name=language][value=${language}]`).click();
    await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
    await audit(page);
  }
  await page.screenshot({path:info.outputPath('cdc-excel-ar.png'),fullPage:true});
});

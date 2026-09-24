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
  await page.locator('.erp-card').first().click();
  await page.getByRole('link',{name:'Déplacer ou dupliquer',exact:true}).first().click();
  await page.locator('[name=action]').selectOption('duplicate');
  await page.locator('[name=position]').fill('1');
  await page.locator('[name=reason]').fill('Besoin technique supplémentaire');
  await page.locator('[name=confirm]').check();
  await submit(page,'.erp-form button[type=submit]');
  await page.getByRole('link',{name:'Déplacer ou dupliquer',exact:true}).first().click();
  const target = await page.locator('[name=destination] option').last().getAttribute('value');
  await page.locator('[name=destination]').selectOption(target);
  await page.locator('[name=position]').fill('1');
  await page.locator('[name=reason]').fill('Répartition dans le second lot');
  await page.locator('[name=confirm]').check();
  await submit(page,'.erp-form button[type=submit]');
  await expect(page).toHaveURL(new RegExp(`/erp/cdc-lots/${target}/$`));
  await page.locator('input[name=q]').fill('introuvable-unique');
  await page.getByRole('button',{name:'Rechercher',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(0);
  await page.goto(dossierURL);
  await expect(page.locator('.erp-heading')).toContainText('Révision 5');
  await page.getByRole('link',{name:'Échanger les lots avec Excel',exact:true}).click();
  for (const [language,title] of [['en','Lots and items — Excel'],['ar','الحصص والمواد — Excel']]) {
    await page.locator(`.topbar button[name=language][value=${language}]`).click();
    await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
    await audit(page);
  }
  await page.screenshot({path:info.outputPath('cdc-excel-ar.png'),fullPage:true});
  expect((await page.goto('/erp/planning/')).status()).toBe(200);
  await audit(page);
});


test('CDC native lifecycle is integrated with PLAGENOR documents and controlled duplication', async ({page}, info) => {
  test.setTimeout(90000);
  expect((await page.request.post('/__e2e__/session/admin_ops/')).status()).toBe(204);
  await page.goto('/erp/cdc/new/');
  await page.locator('.topbar button[name=language][value=fr]').click();
  await page.locator('[name=family]').selectOption('reagents');
  const number = {chromium:8201,firefox:8202,'mobile-chromium':8203}[info.project.name];
  await page.locator('[name=reference]').fill(`${number}/SME/SDFM/SG/ESSBO/2026`);
  await page.locator('[name=title]').fill(`CDC native ${info.project.name}`);
  await submit(page,'.erp-form button[type=submit]');
  await expect(page.getByRole('link',{name:'Pièces jointes',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Créer le plan d’approvisionnement',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Dupliquer de manière contrôlée',exact:true})).toBeVisible();
  await audit(page);

  await page.getByRole('link',{name:'Pièces jointes',exact:true}).click();
  await expect(page).toHaveURL(/\/erp\/resource-documents\/work\/[0-9a-f-]+\/$/);
  await audit(page);
  await page.goBack();

  await page.getByRole('link',{name:'Dupliquer de manière contrôlée',exact:true}).click();
  await page.locator('[name=reference]').fill(`${number + 100}/SME/SDFM/SG/ESSBO/2026`);
  await page.locator('[name=title]').fill(`CDC native copy ${info.project.name}`);
  await page.locator('[name=reason]').fill('Nouvelle opération institutionnelle distincte');
  await submit(page,'.erp-form button[type=submit]');
  await expect(page.locator('.erp-eyebrow')).toContainText(`${number + 100}/SME/SDFM/SG/ESSBO/2026`);

  await page.locator('.topbar button[name=language][value=en]').click();
  await expect(page.getByRole('link',{name:'Attachments',exact:true})).toBeVisible();
  await audit(page);
  await page.locator('.topbar button[name=language][value=ar]').click();
  await expect(page.getByRole('link',{name:'المرفقات',exact:true})).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('dir','rtl');
  await audit(page);
});

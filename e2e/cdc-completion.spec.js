const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const {execFileSync} = require('node:child_process');
test.setTimeout(180000);

async function submit(page, selector) {
  const path = new URL(page.url()).pathname;
  const [response] = await Promise.all([
    page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === path),
    page.waitForNavigation({waitUntil:'domcontentloaded'}),
    page.locator(selector).click(),
  ]);
  expect([302,303]).toContain(response.status());
}

async function audit(page) {
  const result = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
  expect(result.violations.map(v => ({id:v.id,nodes:v.nodes.map(n=>n.target)}))).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
}

test('CDC selective editable reuse and signed financial import are persistent and accessible', async ({page}, info) => {
  expect((await page.request.post('/__e2e__/session/admin_ops/')).status()).toBe(204);
  const number = {chromium:8601,firefox:8602,'mobile-chromium':8603}[info.project.name] + info.retry*10;
  const reference = `${number}/SME/SDFM/SG/ESSBO/2026`;
  async function create(ref, title) {
    await page.goto('/erp/cdc/new/');
    await page.locator('.topbar button[name=language][value=fr]').click();
    await page.locator('[name=family]').selectOption('equipment');
    await page.locator('[name=reference]').fill(ref);
    await page.locator('[name=title]').fill(title);
    await submit(page,'.erp-form button[type=submit]');
    return page.url();
  }
  const source = await create(reference, `Source CDC ${info.project.name}`);
  const target = await create(`${number+100}/SME/SDFM/SG/ESSBO/2026`, `Destination CDC ${info.project.name}`);
  await page.getByRole('link',{name:'Catalogue et réutilisation',exact:true}).click();
  await page.locator('#id_filter_revision').selectOption({label:`${reference} — R1`});
  await page.getByRole('button',{name:'Rechercher',exact:true}).click();
  await page.getByRole('button',{name:'Tout sélectionner',exact:true}).click();
  expect(await page.locator('[name=selections]:checked').count()).toBeGreaterThan(2);
  await page.getByRole('button',{name:'Tout désélectionner',exact:true}).click();
  await expect(page.locator('[name=selections]:checked')).toHaveCount(0);
  await page.locator('[name=selections]').nth(0).check();
  await page.locator('[name=selections]').nth(1).check();
  await page.locator('[name=reason]').fill('Sélection et besoins vérifiés');
  await audit(page);
  await submit(page,'button[type=submit]:has-text("Prévisualiser la réutilisation")');
  await expect(page.getByRole('heading',{name:'Vérifier les articles à réutiliser',exact:true})).toBeVisible();
  await page.locator('[name=form-0-designation]').fill('Copie indépendante E2E');
  await page.locator('[name=form-0-quantity]').fill('7');
  await page.locator('details summary').nth(1).click();
  await page.locator('[name=form-1-omit]').check();
  await page.locator('[name=confirm]').check();
  await audit(page);
  await submit(page,'button[type=submit]:has-text("Confirmer et enregistrer")');
  await expect(page.locator('.erp-heading')).toContainText('Révision 2');
  await page.goto(source);
  await expect(page.locator('.erp-heading')).toContainText('Révision 1');
  await page.goto(target);
  await page.getByRole('link',{name:'Estimations et totaux financiers',exact:true}).click();
  const finance = page.url();
  const [download] = await Promise.all([page.waitForEvent('download'),
    page.getByRole('link',{name:'Exporter le classeur financier',exact:true}).click()]);
  const file = info.outputPath('cdc-finances.xlsx');
  await download.saveAs(file);
  execFileSync('python',['-c',"import sys;from openpyxl import load_workbook;p=sys.argv[1];b=load_workbook(p);s=b.worksheets[0];s['D2']=4;s['E2']=150;s['F2']=19;b.save(p)",file]);
  await page.locator('[name=file]').setInputFiles(file);
  await page.locator('[name=reason]').fill('Devis financier synthétique confirmé');
  await submit(page,'button[type=submit]:has-text("Analyser et prévisualiser")');
  await expect(page.getByRole('heading',{name:'Totaux financiers après import',exact:true})).toBeVisible();
  await expect(page.locator('body')).toContainText('714');
  await audit(page);
  await submit(page,'button[type=submit]:has-text("Confirmer et enregistrer")');
  await page.goto(finance);
  await expect(page.locator('body')).toContainText('714');
  await expect(page.locator('tbody')).toContainText('Copie indépendante E2E');
  await page.reload();
  await expect(page.locator('body')).toContainText('714');

  const pages = [
    ['catalogue/', 'Catalogue and reuse', 'الفهرس وإعادة الاستخدام'],
    ['finances/', 'Financial estimates and totals', 'التقديرات والمجاميع المالية'],
    ['tables/', 'Template tables', 'جداول النموذج'],
    ['import/', 'CDC import centre', 'مركز استيراد دفتر الشروط'],
    ['guide/', 'Terms of reference guide', 'دليل دفتر الشروط'],
  ];
  for (const [language, index] of [['en',1],['ar',2]]) {
    await page.locator(`.topbar button[name=language][value=${language}]`).click();
    for (const entry of pages) {
      await page.goto(target+entry[0]);
      await expect(page.getByRole('heading',{name:entry[index],exact:true})).toBeVisible();
      if (entry[0] === 'tables/') await page.locator('details summary').first().click();
      await audit(page);
    }
    await expect(page.locator('html')).toHaveAttribute('dir',language==='ar'?'rtl':'ltr');
    await page.screenshot({path:info.outputPath(`cdc-guide-${language}.png`),fullPage:true});
  }
});

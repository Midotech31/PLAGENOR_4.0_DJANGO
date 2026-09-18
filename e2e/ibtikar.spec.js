const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

for (const code of ['EGTP-CAN', 'EGTP-SeqS', 'EGTP-Seq02', 'EGTP-PCR', 'EGTP-GDE', 'EGTP-PS', 'EGTP-IMT', 'EGTP-Illumina-Microbial-WGS', 'EGTP-Lyoph', 'EGTP-PSM']) {
  test(`IBTIKAR ${code} editor is available and accessible`, async ({ page }) => {
    await page.goto(`/ibtikar/new/${code}/`);
    await expect(page.locator('#ibk-editor')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(result.violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) }))).toEqual([]);
  });
}

test('IBTIKAR inactive gel fields survive a draft and reopening', async ({ page }) => {
  await page.request.post('/__e2e__/session/amina/');
  await page.goto('/ibtikar/new/EGTP-CAN/');
  const gel = page.locator('[name="parameters-qc_methods"][value="gel"]');
  await gel.check();
  await page.locator('[name="parameters-gel_percentage"]').fill('2');
  await page.locator('#id_parameters-size_marker').fill('Persisted marker');
  await gel.uncheck();
  await expect(page.locator('#id_parameters-size_marker')).toBeHidden();
  await page.locator('button[name="action"][value="draft"]').click();
  await expect(page).toHaveURL(/\/ibtikar\/request\/[0-9a-f-]+\/$/);
  await expect(page.locator('main')).not.toContainText('Persisted marker');
  await page.locator('a[href$="/edit/"]').click();
  await page.locator('[name="parameters-qc_methods"][value="gel"]').check();
  await expect(page.locator('#id_parameters-size_marker')).toHaveValue('Persisted marker');
});

test('IBTIKAR conditional choices and dynamic rows stay consistent', async ({ page }) => {
  page.on('dialog', dialog => dialog.accept());
  await page.goto('/ibtikar/new/EGTP-PCR/');
  await page.locator('[name="parameters-qc_methods"][value="none"]').check();
  await page.locator('[name="parameters-qc_methods"][value="gel"]').check();
  expect(await page.locator('[name="parameters-qc_methods"]').first().evaluate(el => el.checkValidity())).toBe(false);
  await page.goto('/ibtikar/new/EGTP-IMT/');
  await page.locator('[name="samples-0-risk_status"]').selectOption('clinical');
  await expect(page.locator('#id_attachments-biosafety_declaration')).toBeVisible();
  await expect(page.locator('#id_attachments-biosafety_declaration')).toHaveAttribute('required', '');
  await page.locator('[name="samples-0-maldi_target"]').selectOption('reusable');
  expect(await page.locator('[name="samples-0-maldi_target"]').evaluate(el => el.checkValidity())).toBe(false);
  await page.locator('[name="samples-0-maldi_target"]').selectOption('disposable');
  expect(await page.locator('[name="samples-0-maldi_target"]').evaluate(el => el.checkValidity())).toBe(true);
  await page.goto('/ibtikar/new/EGTP-Lyoph/');
  await page.locator('[name="samples-0-container_volume_ml"]').fill('10');
  await page.locator('[name="samples-0-fill_volume_ml"]').fill('6');
  expect(await page.locator('[name="samples-0-fill_volume_ml"]').evaluate(el => el.checkValidity())).toBe(false);
  await page.locator('[name="samples-0-fill_volume_ml"]').fill('5');
  expect(await page.locator('[name="samples-0-fill_volume_ml"]').evaluate(el => el.checkValidity())).toBe(true);
  await page.goto('/ibtikar/new/EGTP-PS/');
  for (let i = 0; i < 8; i++) await page.locator('#ibk-add-sample').click();
  await expect(page.locator('[data-ibk-group="sample"]')).toHaveCount(9);
  await expect(page.locator('[name="samples-TOTAL_FORMS"]')).toHaveValue('9');
});

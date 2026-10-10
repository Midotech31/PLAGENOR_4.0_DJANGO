const {test, expect} = require('@playwright/test');

for (const [language, operationsTitle] of [
  ['fr', 'Organisation de l’analyse'],
  ['en', 'Analysis organisation'],
  ['ar', 'تنظيم التحليل'],
]) {
  test(`MALDI assignment and contextual actions work in ${language} under enforced CSP`, async ({page, context}, info) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await context.addCookies([{name:'django_language',value:language,url:'http://127.0.0.1:8001'}]);
    expect((await page.request.post('/__e2e__/session/admin_ops/')).status()).toBe(204);
    const identifier = `${info.project.name}-${language}`;
    await page.goto('/dashboard/ops/');
    const card = page.locator('.data-card:visible').filter({hasText:`E2E-ASSIGN-${identifier}`});
    await card.locator('a[href^="/dashboard/ops/request/"]').click();
    const response = await page.reload();
    expect(response.headers()['content-security-policy']).toBeTruthy();
    expect(response.headers()['content-security-policy-report-only']).toBeUndefined();
    expect(response.headers()['content-security-policy']).not.toContain('unsafe-eval');

    const assignment = page.locator('#request-assignment');
    const select = assignment.locator('#assignment-member');
    const eligible = select.locator('option').filter({hasText:`Synthetic ${identifier}`});
    await expect(eligible).toHaveCount(1);
    await expect(eligible).not.toHaveAttribute('disabled');
    await expect(select.locator('option[disabled]')).not.toHaveCount(0);
    await expect(page.locator('input[name="to_status"][value="ASSIGNED"]')).toHaveCount(0);
    await select.selectOption(await eligible.getAttribute('value'));
    const submit = assignment.locator('form button[type="submit"]');
    await expect(submit).toBeEnabled();
    const [post] = await Promise.all([
      page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.startsWith('/dashboard/ops/assign/')),
      submit.click(),
    ]);
    expect(post.status()).toBe(302);
    await expect(page.locator('#assignment-member')).toHaveCount(0);
    await page.reload();
    await expect(assignment).toContainText(`Synthetic ${identifier}`);

    const header = await page.locator('.page-header').boundingBox();
    const operations = page.locator('section').filter({has:page.getByRole('heading',{name:operationsTitle,exact:true})});
    await expect(operations).toBeVisible();
    expect((await operations.boundingBox()).y).toBeGreaterThan(header.y + header.height);
    await expect(operations.locator('a')).toHaveCount(3);
    const validationLink = page.locator('main a[href^="/ibtikar/request/"]');
    await expect(validationLink).toHaveCount(1);
    const documents = page.locator('.card').filter({has:page.locator('a[href^="/ibtikar/request/"]')});
    await expect(documents.locator('.card-header h3')).toBeVisible();
    expect((await documents.boundingBox()).y).toBeGreaterThan(header.y + header.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);

    // Reassignment stays collapsed until explicitly opened under the CSP build.
    await expect(page.locator('#reassignment-member')).toBeHidden();
    await assignment.locator('button[type="button"]').click();
    await expect(page.locator('#reassignment-member')).toBeVisible();
    await assignment.locator('button[type="button"]').click();
    await expect(page.locator('#reassignment-member')).toBeHidden();
    expect(errors).toEqual([]);
  });
}

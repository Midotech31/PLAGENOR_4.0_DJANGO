const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

async function login(page, username) {
  expect((await page.request.post(`/__e2e__/session/${username}/`)).status()).toBe(204);
}
async function french(page) {
  await page.goto('/erp/planning/');
  const control = page.locator('.topbar button[name=language][value=fr]');
  if (await control.count()) await control.click();
}
async function post(page, selector) {
  const path=new URL(page.url()).pathname;
  const [response]=await Promise.all([
    page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path),
    page.locator(selector).click()
  ]);
  expect([302,303],`Form response ${response.status()}`).toContain(response.status());
  await page.waitForLoadState('domcontentloaded');
}
async function audit(page) {
  const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
  expect(result.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
}
function local(value) {
  const parts=new Intl.DateTimeFormat('sv-SE',{timeZone:'Africa/Algiers',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(value);
  return parts.replace(' ','T');
}

test('Admin Ops assigns, checks, starts and approves one centrally scheduled activity',async({page},info)=>{
  test.setTimeout(120000);
  const suffix=`P${Date.now().toString(36)}${info.project.name.slice(0,3)}`.toUpperCase();
  await login(page,'admin_ops');
  await french(page);
  await page.goto('/erp/planning/resources/new/');
  await page.locator('[name=code]').fill(suffix);
  await page.locator('[name=name]').fill(`Instrument ${suffix}`);
  await page.locator('[name=kind]').selectOption('EQUIPMENT');
  await post(page,'.erp-form button[type=submit]');
  await page.goto('/erp/planning/new/');
  await page.locator('[name=kind]').selectOption('QUALITY');
  await page.locator('[name=title]').fill(`Activity ${suffix}`);
  const options=await page.locator('[name=assignee] option').evaluateAll(nodes=>nodes.map(n=>({value:n.value,text:n.textContent})));
  const finance=options.find(o=>/financi/i.test(o.text));
  expect(finance,'seeded finance team account').toBeTruthy();
  await page.locator('[name=assignee]').selectOption(finance.value);
  await page.locator('[name=starts_at]').fill(local(new Date(Date.now()-5*60000)));
  await page.locator('[name=ends_at]').fill(local(new Date(Date.now()+55*60000)));
  await page.locator('[name=resources]').selectOption({label:`${suffix} — Instrument ${suffix}`});
  await page.locator('[name=instructions]').fill('Verify the documented quality checks and record the result.');
  await post(page,'.erp-form button[type=submit]');
  await expect(page).toHaveURL(/\/erp\/planning\/activities\/[0-9a-f-]+\/$/);
  const activityURL=new URL(page.url()).pathname;
  const workID=activityURL.split('/').filter(Boolean).pop();
  await expect(page.locator('.erp-heading h1')).toHaveText(`Activity ${suffix}`);
  await audit(page);
  await page.screenshot({path:info.outputPath('activity-readiness.png'),fullPage:true});
  await page.goto('/erp/planning/');
  await expect(page.locator('.planning-slot').filter({hasText:`Activity ${suffix}`})).toHaveCount(1);
  await audit(page);
  await page.screenshot({path:info.outputPath('planning-workspace.png'),fullPage:true});
  await login(page,'finance');
  await page.goto(activityURL);
  await page.locator('[name=note]').fill('Instrument, supplies and procedure checked.');
  await page.locator('[name=confirmed]').check();
  await post(page,'.erp-form button[type=submit]');
  await expect(page.locator('.planning-ready')).toBeVisible();
  expect((await page.request.get(`/erp/tasks/${workID}/delegate/`)).status()).toBe(403);
  await page.goto(`/erp/tasks/${workID}/`);
  await page.locator('[name=state]').selectOption('IN_PROGRESS');
  await post(page,'.erp-form button');
  await page.locator('[name=state]').selectOption('SUBMITTED');
  await page.locator('[name=reason]').fill('Quality checks completed; documented result is compliant.');
  await post(page,'.erp-form button');
  await expect(page.locator('[name=state]')).toHaveCount(0);
  await login(page,'admin_ops');
  await page.goto('/erp/planning/');
  await expect(page.locator('#planning-review')).toContainText(`Activity ${suffix}`);
  await page.goto(`/erp/tasks/${workID}/`);
  await page.locator('[name=state]').selectOption('APPROVED');
  await page.locator('[name=reason]').fill('Completion report reviewed and approved.');
  await post(page,'.erp-form button');
  await page.goto(activityURL);
  await expect(page.locator('.erp-heading')).toContainText('Validé');
  await expect(page.locator('[name=confirmed]')).toHaveCount(0);
  await audit(page);
  await page.screenshot({path:info.outputPath('activity-approved.png'),fullPage:true});
});

for(const [language,title,direction] of [['en','Planning & activities','ltr'],['ar','التخطيط والأنشطة','rtl']]) {
  test(`Central planning is translated and accessible in ${language}`,async({page},info)=>{
    await login(page,'admin_ops');
    await page.goto('/erp/planning/');
    await page.locator(`.topbar button[name=language][value=${language}]`).click();
    await expect(page.locator('html')).toHaveAttribute('dir',direction);
    await expect(page.locator('.erp-heading h1')).toHaveText(title);
    await audit(page);
    await page.screenshot({path:info.outputPath(`planning-${language}.png`),fullPage:true});
    await page.goto('/erp/planning/new/');
    await audit(page);
    await page.screenshot({path:info.outputPath(`planning-form-${language}.png`),fullPage:true});
  });
}

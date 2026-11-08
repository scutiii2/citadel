import { expect, test, type Page } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";
const row = (page: Page, label: string) => page.locator('article.catalog-row').filter({has:page.getByRole('button',{name:`View ${label}`,exact:true})});

test('shared capabilities are managed by administrators, so the list has no switch for them',async({page})=>{
 const api=await installFakeApi(page,{admin:true});await logIn(page);await page.goto('/capabilities');
 const pdf=row(page,'PDF files');await expect(pdf).toBeVisible();await expect(pdf.getByRole('switch')).toHaveCount(0);
 await pdf.getByRole('button',{name:'View PDF files',exact:true}).click();await expect(page.locator('.account-control')).toHaveCount(0);expect(api.unexpected).toEqual([]);
});
test('old Supermarket links redirect and shared extensions have no switch either',async({page})=>{
 const api=await installFakeApi(page,{admin:true});await page.route('**/api/extensions',route=>route.fulfill({json:[{id:'echo',label:'Echo server',description:'',status:'connected',error:null,tools:[]}]}));await logIn(page);await page.goto('/capabilities/supermarket?tab=extensions');await expect(page).toHaveURL(/\/capabilities\?tab=extensions$/);
 const echo=row(page,'Echo server');await expect(echo).toContainText('Enabled');await expect(echo.getByRole('switch')).toHaveCount(0);expect(api.unexpected).toEqual([]);
});
test('private extensions are added, enabled, edited and removed from the Extensions tab',async({page})=>{
 const api=await installFakeApi(page);await logIn(page);await page.goto('/capabilities?tab=extensions');await page.getByRole('button',{name:'+ Add extension',exact:true}).click();await page.getByLabel('Label',{exact:true}).fill('My notes');await page.getByLabel('Address',{exact:true}).fill('https://notes.example.com/mcp');await page.getByRole('button',{name:'Add header',exact:true}).click();await page.locator('.header-name').fill('Authorization');await page.locator('.header-value').fill('Bearer example');await page.getByRole('dialog',{name:'Add your own extension'}).getByRole('button',{name:'Add',exact:true}).click();
 const mine=row(page,'My notes');await expect(mine).toContainText('Disabled');await mine.locator('label.toggle').click();await expect(mine.getByRole('switch')).toBeChecked();await mine.getByRole('button',{name:'View My notes',exact:true}).click();await page.getByRole('button',{name:'Edit connection',exact:true}).click();const editor=page.getByRole('dialog',{name:'Edit private extension'});await expect(editor.getByText(/Their values are never shown/)).toBeVisible();await editor.getByRole('button',{name:'Cancel',exact:true}).click();await page.locator('.danger-zone summary').click();await page.getByRole('button',{name:'Remove extension',exact:true}).click();await expect(page.getByRole('dialog',{name:'Remove private extension'})).toBeVisible();await page.getByRole('button',{name:'Remove',exact:true}).click();await expect(mine).toHaveCount(0);expect(api.userExtensions.size).toBe(0);expect(api.unexpected).toEqual([]);
});
for(const width of [1280,768,767,375,320])test(`two-tab tool workspace works at ${width}px in both themes`,async({page},info)=>{
 const api=await installFakeApi(page,{admin:true});await page.setViewportSize({width,height:850});await logIn(page);await page.goto('/capabilities');
 for(const theme of ['dark','light']){
  await page.evaluate(theme=>{document.documentElement.style.colorScheme=theme;},theme);
  await expect(page.getByRole('tab',{name:'Capabilities',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.screenshot({path:info.outputPath(`list-${theme}.png`)});await row(page,'PDF files').getByRole('button',{name:'View PDF files',exact:true}).click();await expect(page.locator('.detail-title')).toHaveText('PDF files');if(width<768)await expect(page.locator('.back')).toBeVisible();else await expect(page.locator('.back')).toBeHidden();
  await page.locator('.detail .tool-list button').first().click();const dialog=page.getByRole('dialog').filter({has:page.getByRole('button',{name:'Run',exact:true})});await expect(dialog).toBeVisible();
  if(width<768){const box=await dialog.boundingBox();const nav=await page.locator('aside.rail').boundingBox();expect(box!.y+box!.height).toBeLessThanOrEqual(nav!.y+1);}
  await page.screenshot({path:info.outputPath(`capabilities-${theme}.png`)});
  await dialog.getByRole('button',{name:'Close',exact:true}).click();if(width<768)await page.getByRole('button',{name:'‹ Capabilities',exact:true}).click();await page.getByRole('tab',{name:'Extensions',exact:true}).click();await page.getByRole('tab',{name:'Capabilities',exact:true}).click();
 }
 expect(api.unexpected).toEqual([]);
});

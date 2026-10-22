import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useAccountCapabilitiesStore } from "../stores/accountCapabilities";
import CapabilitiesView from "./CapabilitiesView.vue";

const api = vi.hoisted(() => ({ caps: vi.fn(), commands: vi.fn(), tools: vi.fn(), resources: vi.fn(), extensions: vi.fn(), get: vi.fn(), set: vi.fn(), privateList: vi.fn(), update: vi.fn(), remove: vi.fn(), read: vi.fn(), run: vi.fn() }));
vi.mock("../api/CommandsClient", () => ({ commandsClient: { capabilities: api.caps, list: api.commands } }));
vi.mock("../api/ExtensionsClient", async original => ({ ...await original<typeof import('../api/ExtensionsClient')>(), extensionsClient: { list: api.extensions } }));
vi.mock("../api/AccountCapabilitiesClient", () => ({ accountCapabilitiesClient: { get: api.get, set: api.set } }));
vi.mock("../api/UserExtensionsClient", () => ({ userExtensionsClient: { list: api.privateList, update: api.update, remove: api.remove } }));
vi.mock("../api/McpServerClient", () => ({ McpServerClient: class { listTools=api.tools; listResources=api.resources; readResource=api.read; runTool=api.run; } }));
const mine = { id:'mine', label:'My server', description:'Personal documents', url:'https://example.com/mcp', header_names:[], enabled:false, status:'connected', error:null, tools:['search'] };
beforeEach(() => {
  vi.clearAllMocks();
  api.commands.mockResolvedValue([{capability:'notes',name:'save',tool_name:'save',description:'Save note'}]);
  HTMLDialogElement.prototype.showModal=function(){ this.setAttribute('open',''); };
  HTMLDialogElement.prototype.close=function(){ this.removeAttribute('open'); };
  api.caps.mockResolvedValue([
    {name:'notes',label:'Notes',enabled:true,tools:['save'],resources:['help']},
    {name:'gen',label:'Generator',enabled:true,tools:['password'],resources:[]},
    {name:'offline',label:'Offline capability',enabled:false,tools:[],resources:[]},
  ]);
  api.tools.mockResolvedValue([{name:'save',title:'Save note',description:'Write a note',inputSchema:{type:'object',properties:{}}}]);
  api.resources.mockResolvedValue([{name:'help',uri:'help://notes',template:false}]);
  api.extensions.mockResolvedValue([{id:'echo',label:'Echo',description:'',status:'connected',error:null,tools:[]},{id:'down',label:'Down server',description:'',status:'error',error:'Refused',tools:['down__run']}]);
  api.get.mockResolvedValue({capabilities:['notes'],extensions:['echo'],disabled_tools:[]});
  api.privateList.mockResolvedValue([mine]);
  api.update.mockImplementation(async (id,patch) => ({...mine,id,...patch}));
  api.remove.mockResolvedValue(undefined);
  api.set.mockImplementation(async (kind,key,on) => {
    const account=useAccountCapabilitiesStore(), caps=new Set(account.capabilities), exts=new Set(account.extensions), target=kind==='capability'?caps:exts;
    if(on)target.add(key);else target.delete(key);
    return {capabilities:[...caps],extensions:[...exts],disabled_tools:[]};
  });
  api.read.mockResolvedValue('Help text');api.run.mockResolvedValue({text:'Saved',isError:false});
});
async function show(permissions=['chat.use','tools.view','tools.execute','extensions.personal.manage']) {
  const pinia=createPinia();setActivePinia(pinia);
  useAuthStore().account={id:1,username:'test',email:'t@example.com',email_verified:true,roles:[],permissions};
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/capabilities',component:CapabilitiesView},...["/notes","/generator"].map(path=>({path,component:{template:'<div/>'}}))]});await router.push('/capabilities');
  const w=mount(CapabilitiesView,{global:{plugins:[pinia,router]}});await flushPromises();return w;
}
type Wrapper=Awaited<ReturnType<typeof show>>;
const names=(w:Wrapper)=>w.findAll('.catalog-row .row-title').map(r=>r.text());
const row=(w:Wrapper,name:string)=>w.findAll('.catalog-row').find(r=>r.get('.row-title').text()===name)!;
const tab=(w:Wrapper,name:string)=>w.findAll('[role=tab]').find(t=>t.text()===name)!;
const choose=(w:Wrapper,name:string)=>row(w,name).get('button.item-link').trigger('click');

it('uses two tabs, keeps disabled capabilities below enabled ones and labels offline items',async()=>{
  const w=await show();expect(w.findAll('[role=tab]').map(t=>t.text())).toEqual(['Capabilities','Extensions']);
  expect(names(w)).toEqual(['Notes','Generator','Offline capability']);
  expect(row(w,'Generator').classes()).toContain('disabled');expect(row(w,'Offline capability').classes()).toContain('offline');
  expect(row(w,'Offline capability').text()).toContain('Offline');expect(w.text()).not.toContain('Supermarket');
  await tab(w,'Extensions').trigger('click');expect(names(w)).toEqual(['Echo','My server','Down server']);
});
it('saves switches without removing rows and holds confirmed state while pending',async()=>{
  let done!:(v:unknown)=>void;api.set.mockImplementation(()=>new Promise(yes=>{done=yes;}));const w=await show();
  await row(w,'Generator').get('input').setValue(true);await flushPromises();
  expect(row(w,'Generator').text()).toContain('Disabled');expect(row(w,'Generator').attributes('aria-busy')).toBe('true');
  expect((row(w,'Generator').get('input').element as HTMLInputElement).checked).toBe(false);
  done({capabilities:['notes','gen'],extensions:['echo'],disabled_tools:[]});await flushPromises();
  expect(row(w,'Generator').classes()).not.toContain('disabled');expect(names(w)).toContain('Generator');
});
it('retains tab searches and selection while supporting keyboard tabs',async()=>{
  const w=await show();await w.get('input[type=search]').setValue('write');expect(names(w)).toEqual(['Notes']);
  await choose(w,'Notes');await tab(w,'Extensions').trigger('click');expect((w.get('input[type=search]').element as HTMLInputElement).value).toBe('');
  await tab(w,'Extensions').trigger('keydown',{key:'ArrowLeft'});expect((w.get('input[type=search]').element as HTMLInputElement).value).toBe('write');expect(w.get('.detail-title').text()).toBe('Notes');
});
it('keeps offline and private tools unavailable and private management permission gated',async()=>{
  const w=await show();await tab(w,'Extensions').trigger('click');await choose(w,'Down server');
  expect(w.get('.tool-list button').attributes('disabled')).toBeDefined();expect(w.text()).toContain('Refused');
  await choose(w,'My server');expect(w.get('.tool-list button').attributes('disabled')).toBeDefined();expect(w.text()).toContain('always ask first');
  await row(w,'My server').get('input').setValue(true);await flushPromises();expect(api.update).toHaveBeenCalledWith('mine',{enabled:true});
  const readonly=await show(['chat.use']);expect(names(readonly)).toContain('Echo');expect(readonly.find('.add-extension').exists()).toBe(false);
  await choose(readonly,'My server');expect(readonly.find('.edit-extension').exists()).toBe(false);
});
it('ignores late resource results after selecting another capability',async()=>{
  let done!:(v:string)=>void;api.read.mockImplementation(()=>new Promise<string>(yes=>{done=yes;}));
  const w=await show();await choose(w,'Notes');await w.get('.resource-link').trigger('click');await choose(w,'Generator');done('Previous private content');await flushPromises();expect(w.text()).not.toContain('Previous private content');
});
it('retains slash command discovery and copying in tool details',async()=>{
  const w=await show();await choose(w,'Notes');await w.get('.tool-list button').trigger('click');await flushPromises();
  expect(w.get('dialog .tool-command').text()).toContain('/notes save');
  expect(w.find('button[aria-label="Copy command"]').exists()).toBe(true);
});
it('keeps built-in tools usable when the shared extension catalog is unavailable',async()=>{
  api.extensions.mockRejectedValue(new Error('Extension discovery unavailable'));
  const w=await show();expect(names(w)).toContain('Notes');await choose(w,'Notes');
  expect(w.get('.tool-list button').attributes('disabled')).toBeUndefined();
  await tab(w,'Extensions').trigger('click');expect(w.text()).toContain('Extension discovery unavailable');
});
it('clears a tool preview when navigation selects another integration',async()=>{
  const w=await show();await choose(w,'Notes');await w.get('.tool-list button').trigger('click');
  await choose(w,'Generator');expect(w.findComponent({name:'ToolRunModal'}).props('tool')).toBeNull();
});

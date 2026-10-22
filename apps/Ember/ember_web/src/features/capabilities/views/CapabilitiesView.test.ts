import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import type { Account } from "../../../api/auth/AuthClient";
import type { CapabilityInfo } from "../../../api/tools/CommandsClient";
import type { UserExtension } from "../api/UserExtensionsClient";
import type { ResourceInfo, ToolInfo } from "../../../api/types";
import ConfirmModal from "../../../components/ui/dialogs/ConfirmModal.vue";
import { useAuthStore } from "../../../stores/auth";
import { useAccountCapabilitiesStore } from "../stores/accountCapabilities";
import CapabilitiesView from "./CapabilitiesView.vue";

const mocks = vi.hoisted(() => ({
  capabilities: vi.fn(),
  setCapability: vi.fn(),
  listTools: vi.fn(),
  listResources: vi.fn(),
  readResource: vi.fn(),
  runTool: vi.fn(),
  extensions: vi.fn(),
  accountGet: vi.fn(),
  accountSet: vi.fn(),
  userList: vi.fn(),
  userUpdate: vi.fn(),
}));

vi.mock("../api/ExtensionsClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/ExtensionsClient")>()),
  extensionsClient: { list: mocks.extensions, remove: vi.fn(), add: vi.fn() },
}));

vi.mock("../../../api/tools/CommandsClient", () => ({
  commandsClient: { capabilities: mocks.capabilities, setCapability: mocks.setCapability },
}));
vi.mock("../../../api/tools/McpServerClient", () => ({
  McpServerClient: class {
    listTools = mocks.listTools;
    listResources = mocks.listResources;
    readResource = mocks.readResource;
    runTool = mocks.runTool;
  },
}));

vi.mock("../api/AccountCapabilitiesClient", () => ({
  accountCapabilitiesClient: { get: mocks.accountGet, set: mocks.accountSet },
}));
vi.mock("../api/UserExtensionsClient", () => ({
  userExtensionsClient: { list: mocks.userList, create: vi.fn(), update: mocks.userUpdate, remove: vi.fn() },
}));

const tool = (name: string, title: string, description = ""): ToolInfo => ({
  name,
  title,
  description,
  inputSchema: { type: "object", properties: {} },
});

const CAPS: CapabilityInfo[] = [
  { name: "pdf", enabled: true, label: "PDF files", tools: ["tool_pdf_merge", "tool_pdf_split"], resources: ["pdf_help"], has_gui: true },
  { name: "services", enabled: true, label: null, tools: ["tool_srv_restart"], resources: [] },
  { name: "legacy", enabled: false, label: "Legacy", tools: [], resources: [] },
];
const TOOLS = [
  tool("tool_pdf_merge", "Merge", "Join PDFs"),
  tool("tool_pdf_split", "Split"),
  tool("tool_srv_restart", "Restart Service"),
  tool("ext__echo", "Echo"),
];
const RESOURCES: ResourceInfo[] = [{ uri: "help://pdf", name: "pdf_help", description: "How to merge", template: false }];
const MINE: UserExtension = {
  id: "mynotes",
  label: "My notes",
  description: "Notes on my server",
  url: "https://notes.example.com/mcp",
  header_names: [],
  enabled: true,
  status: "connected",
  error: null,
  tools: ["search", "add"],
};

const ACCOUNT: Account = {
  id: 1,
  username: "lex",
  email: "lex@example.com",
  email_verified: true,
  roles: [],
  permissions: ["chat.use", "tools.view", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage"],
};

async function show(options: { admin?: boolean; query?: string; permissions?: string[]; attach?: boolean; added?: { capabilities?: string[]; extensions?: string[] }; userExtensions?: UserExtension[] } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = {
    ...ACCOUNT,
    permissions: options.permissions ?? (options.admin ? ["chat.use", "tools.view", "roles.manage", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage"] : ["chat.use", "tools.view", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage"]),
  };
  const listedExtensions = (await Promise.resolve(mocks.extensions()).catch(() => [])) as { id: string }[];
  mocks.accountGet.mockResolvedValue({
    capabilities: options.added?.capabilities ?? CAPS.map((c) => c.name),
    extensions: options.added?.extensions ?? listedExtensions.map((e) => e.id),
    disabled_tools: [],
  });
  mocks.userList.mockResolvedValue(options.userExtensions ?? []);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...["/notes", "/memory", "/generator", "/tickets"].map(path => ({path, component: {template:"<div/>"}})),
      { path: "/capabilities", component: CapabilitiesView },
      { path: "/capabilities/supermarket", component: { template: "<div />" } },
      { path: "/capabilities/:name", component: { template: "<div />" } },
    ],
  });
  await router.push(options.query ? `/capabilities?q=${options.query}` : "/capabilities");
  const wrapper = mount(CapabilitiesView, {
    attachTo: options.attach ? document.body : undefined,
    global: { plugins: [pinia, router] },
  });
  await flushPromises();
  return wrapper;
}

type Wrapper = Awaited<ReturnType<typeof show>>;
const row = (w: Wrapper, label: string) => w.findAll(".catalog-row").find(r => r.get(".row-title").text() === label)!;
const choose = (w: Wrapper, label: string) => row(w, label).get("button.item-link").trigger("click");
const extensionsTab = (w: Wrapper) => w.get("#caps-tab-extensions").trigger("click");
const EXT = {id:"ext",label:"Echo server",description:"Documents",status:"connected",error:null,tools:["ext__echo"],web_url:"https://echo.example/app"};
beforeEach(() => {
  HTMLDialogElement.prototype.showModal=function(){this.setAttribute("open","");};
  HTMLDialogElement.prototype.close=function(){this.removeAttribute("open");};
  vi.clearAllMocks();
  mocks.capabilities.mockResolvedValue(CAPS);mocks.listTools.mockResolvedValue(TOOLS);mocks.listResources.mockResolvedValue(RESOURCES);mocks.extensions.mockResolvedValue([EXT]);
  mocks.runTool.mockResolvedValue({text:"merged ok",isError:false});mocks.readResource.mockResolvedValue("# Help text");
  mocks.userUpdate.mockImplementation(async (id,patch)=>({...MINE,id,...patch}));
  mocks.accountSet.mockImplementation(async(kind,key,on)=>{const store=useAccountCapabilitiesStore();const capabilities=new Set(store.capabilities),extensions=new Set(store.extensions),target=kind==="capability"?capabilities:extensions;if(on)target.add(key);else target.delete(key);return {capabilities:[...capabilities],extensions:[...extensions],disabled_tools:[]};});
});

describe("Capabilities tool and workspace access",()=>{
  it("opens the native PDF workspace when the account has access",async()=>{
    const w=await show();await choose(w,"PDF files");expect(w.get('.detail-footer a').attributes('href')).toBe('/capabilities/pdf_merger');
    const readonly=await show({permissions:['tools.view']});await choose(readonly,'PDF files');expect(readonly.find('.detail-footer a').exists()).toBe(false);
  });
  it("links dedicated notes, memory, generator and ticket pages through their permissions",async()=>{
    const definitions=[['notes','Notes','/notes'],['memory','Memory','/memory'],['gen','Generator','/generator'],['ticket','Tickets','/tickets']];
    mocks.capabilities.mockResolvedValue(definitions.map(([name,label])=>({name,label,enabled:true,tools:[],resources:[]})));
    const w=await show({permissions:['tools.view','chat.use','tools.execute','tickets.create'],added:{capabilities:definitions.map(d=>d[0]!)}});
    for(const [,label,path] of definitions){await choose(w,label!);expect(w.get('.detail-footer a').attributes('href')).toBe(path);}
  });
  it("retains generic GUI page fallback and suppresses links for disabled subscriptions",async()=>{
    mocks.capabilities.mockResolvedValue([{name:'custom',label:'Custom',enabled:true,tools:[],resources:[],has_gui:true}]);
    const w=await show({added:{capabilities:['custom']}});await choose(w,'Custom');expect(w.get('.detail-footer a').attributes('href')).toBe('/capabilities/custom');
    const disabled=await show({added:{capabilities:[]}});await choose(disabled,'Custom');expect(disabled.find('.detail-footer a').exists()).toBe(false);
  });
  it("opens external apps in a safe new tab, rejecting unsafe URLs and offline servers",async()=>{
    const w=await show();await extensionsTab(w);await choose(w,'Echo server');const link=w.get('.detail-footer a');expect(link.attributes('target')).toBe('_blank');expect(link.attributes('rel')).toBe('noopener noreferrer');
    mocks.extensions.mockResolvedValue([{...EXT,web_url:'javascript:alert(1)'}]);const unsafe=await show();await extensionsTab(unsafe);await choose(unsafe,'Echo server');expect(unsafe.find('.detail-footer a').exists()).toBe(false);
    mocks.extensions.mockResolvedValue([{...EXT,status:'error',error:'refused'}]);const offline=await show();await extensionsTab(offline);await choose(offline,'Echo server');expect(offline.find('.detail-footer a').exists()).toBe(false);expect(offline.text()).toContain('refused');
  });
  it("keeps legacy PDF extension links tied to native capability access",async()=>{
    mocks.extensions.mockResolvedValue([{...EXT,id:'pdf_merger',label:'PDF extension',tools:[]}]);
    const w=await show();await extensionsTab(w);await choose(w,'PDF extension');expect(w.get('.detail-footer a').attributes('href')).toBe('/capabilities/pdf_merger');
    const noAccess=await show({added:{capabilities:[]}});await extensionsTab(noAccess);await choose(noAccess,'PDF extension');expect(noAccess.find('.detail-footer a').exists()).toBe(false);
  });
  it("runs selected tools and shows results, then clears them on close",async()=>{
    const w=await show();await choose(w,'PDF files');await w.get('.tool-list button').trigger('click');await flushPromises();await w.get('form.tool-form').trigger('submit');await flushPromises();expect(mocks.runTool).toHaveBeenCalledWith('tool_pdf_merge',{});expect(w.text()).toContain('merged ok');
    await w.get('dialog button.close').trigger('click');await w.get('.tool-list button').trigger('click');expect(w.text()).not.toContain('merged ok');
  });
  it("lets read-only accounts inspect tools but offers no run form",async()=>{
    const w=await show({permissions:['tools.view']});await choose(w,'PDF files');await w.get('.tool-list button').trigger('click');await flushPromises();expect(w.text()).toContain('tool_pdf_merge');expect(w.find('form.tool-form').exists()).toBe(false);expect(mocks.runTool).not.toHaveBeenCalled();
  });
  it("reads capability resources and keeps namespaced extension resources with their owner",async()=>{
    mocks.listResources.mockResolvedValue([...RESOURCES,{name:'ext__doc',uri:'ext://doc',description:'',template:false}]);const w=await show();await choose(w,'PDF files');await w.get('.resource-link').trigger('click');await flushPromises();expect(mocks.readResource).toHaveBeenCalledWith('help://pdf');expect(w.text()).toContain('Help text');await extensionsTab(w);await choose(w,'Echo server');expect(w.get('.resources').text()).toContain('ext__doc');expect(w.get('.resources').text()).not.toContain('pdf_help');
  });
  it("keeps unclaimed tools while excluding tools owned by a disabled capability",async()=>{
    mocks.extensions.mockResolvedValue([]);const w=await show({added:{capabilities:[]}});await choose(w,'Other tools');expect(w.get('.tool-list').text()).toContain('Echo');expect(w.get('.tool-list').text()).not.toContain('Merge');
  });
  it("offers private editing and confirms removal without any private run action",async()=>{
    const w=await show({permissions:['tools.view','chat.use','extensions.personal.manage'],userExtensions:[MINE]});await extensionsTab(w);await choose(w,'My notes');expect(w.findAll('.tool-list button').every(b=>b.attributes('disabled')!==undefined)).toBe(true);await w.get('.edit-extension').trigger('click');expect(w.findComponent({name:'UserExtensionModal'}).props('extension').id).toBe('mynotes');await w.findComponent({name:'UserExtensionModal'}).vm.$emit('close');await w.get('.remove-extension').trigger('click');expect(w.findComponent(ConfirmModal).props('open')).toBe(true);
  });
  it("shows tool discovery failure while preserving the catalog, and retries failed catalog loads",async()=>{
    mocks.listTools.mockRejectedValue(new Error('Tool schemas unavailable'));const w=await show();expect(row(w,'PDF files')).toBeDefined();expect(w.text()).toContain('Tool schemas unavailable');mocks.capabilities.mockRejectedValue(new Error('Server down'));const failed=await show();expect(failed.text()).toContain('Server down');expect(failed.find('button.retry').exists()).toBe(true);
  });
  it("shows failed saves while restoring the server's subscription state",async()=>{
    mocks.accountSet.mockRejectedValue(new Error('Save refused'));const w=await show({added:{capabilities:['pdf']}});await row(w,'services').get('input').setValue(true);await flushPromises();expect(row(w,'services').text()).toContain('Disabled');expect(w.text()).toContain('Save refused');
  });
});

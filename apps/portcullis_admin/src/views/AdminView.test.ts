import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { adminClient } from "../api/AdminClient";
import { useAuthStore } from "../stores/auth";
import AdminView from "./AdminView.vue";
import OverviewView from "./OverviewView.vue";
import AdminNav from "../components/AdminNav.vue";

vi.mock("../api/AdminClient", () => ({ adminClient: { summary: vi.fn() } }));
const client = vi.mocked(adminClient);
const mounted: ReturnType<typeof mount>[] = [];
afterEach(() => mounted.splice(0).forEach((wrapper) => wrapper.unmount()));
beforeEach(() => {
  setActivePinia(createPinia());
  useAuthStore().account = { id: 1, username: "admin", email: "a@example.com", email_verified: true, roles: [], permissions: ["accounts.view", "roles.view", "invites.manage", "settings.manage"] };
  client.summary.mockReset();
  client.summary.mockResolvedValue({ accounts: 24, unverified: 3, disabled: 1, open_invites: 5, roles: 2 });
});
async function view(path = '/overview') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/overview', component: OverviewView }, { path: '/', redirect: '/overview' }, { path: "/admin", component: AdminView, children: [
    { path: '', redirect: '/overview' },
    { path: 'roles', component: { template: '<div>roles page</div>' } },
    { path: 'accounts', component: { template: '<div>accounts page</div>' } },
    { path: 'invites', component: { template: '<div>invites page</div>' } },
    { path: 'settings', component: { template: '<div>settings page</div>' } },
  ] }, { path: '/:pathMatch(.*)*', component: { template: '<div />' } }] });
  await router.push(path);
  const wrapper = mount({ components: { AdminNav }, template: '<div><AdminNav :expanded="false" /><RouterView /></div>' }, { global: { plugins: [router] } });
  mounted.push(wrapper);
  await flushPromises();
  return { wrapper, router };
}
it('shows separate destinations and marks the active child page', async () => {
  const { wrapper, router } = await view('/admin/roles');
  expect(wrapper.get('nav[aria-label="Admin sections"] a[aria-current="page"]').attributes('aria-label')).toBe('Roles & permissions');
  expect(wrapper.find('.admin-sidebar').exists()).toBe(false);
  expect(wrapper.text()).toContain('roles page');
  expect(client.summary).not.toHaveBeenCalled();
  await router.push('/admin/accounts');
  expect(wrapper.get('nav[aria-label="Admin sections"] a[aria-current="page"]').attributes('aria-label')).toBe('Users');
});
it('shows counts only on the overview and refreshes when returning', async () => {
  const { wrapper, router } = await view();
  expect(wrapper.findAll('.stats .tile').map(t => t.text())).toEqual(['Users24', 'Unverified3', 'Disabled1', 'Open invites5']);
  expect(wrapper.findAll('.destination .live').map(t => t.text())).toContain('24 users · 3 unverified · 1 disabled');
  expect(wrapper.get('.attention a').attributes('href')).toBe('/admin/accounts?status=unverified');
  await router.push('/admin/roles');
  expect(wrapper.find('.stats').exists()).toBe(false);
  await router.push('/admin');
  await flushPromises();
  expect(client.summary).toHaveBeenCalledTimes(2);
});
it('keeps navigation and destination links usable when summary fails', async () => {
  client.summary.mockRejectedValue(new Error('boom'));
  const { wrapper } = await view();
  expect(wrapper.get('[role="alert"]').text()).toContain('boom');
  expect(wrapper.findAll('.destination')).toHaveLength(4);
  expect(wrapper.findAll('.stats .tile .unavailable')).toHaveLength(4);
});
it('shows a count the server withheld as unavailable, not zero', async () => {
  client.summary.mockResolvedValue({ accounts: 24, unverified: null, disabled: 0, open_invites: null, roles: 2 });
  const { wrapper } = await view();
  expect(wrapper.findAll('.stats .tile').map(t => t.text())).toEqual(['Users24', 'UnverifiedUnavailable', 'Disabled0', 'Open invitesUnavailable']);
});
it('offers only overview and roles to a role viewer and hides unrelated counts', async () => {
  useAuthStore().account!.permissions = ['roles.view'];
  const { wrapper } = await view();
  expect(wrapper.findAll('nav[aria-label="Admin sections"] a').map(a => a.attributes('aria-label'))).toEqual(['Overview', 'Roles & permissions']);
  expect(wrapper.findAll('.destination')).toHaveLength(1);
  expect(wrapper.find('.stats').exists()).toBe(false);
  expect(wrapper.find('.page-head .primary').exists()).toBe(false);
});
it('opens invite creation from the overview header', async () => {
  const { wrapper } = await view();
  expect(wrapper.get('.admin-panel-head a[aria-label="Invite member"]').attributes('href')).toBe('/admin/invites?create=1');
  expect(wrapper.get('.admin-panel-head a[aria-label="Invite member"]').attributes('title')).toBe('Invite member');
});

it('keeps overview destinations in sync with available sidebar pages', async () => {
  useAuthStore().account!.permissions = ['accounts.view', 'roles.view', 'invites.manage', 'settings.manage'];
  const { wrapper } = await view();
  const links = wrapper.findAll('.destination').map(a => a.attributes('href'));
  expect(links).toEqual(wrapper.findAll('nav[aria-label="Admin sections"] a').map(a => a.attributes('href')).filter(href => href !== '/overview'));
  expect(links).toContain('/admin/invites');
  expect(links).toContain('/admin/settings');
  expect(wrapper.findAll('.destination p').every(p => p.text().length > 0)).toBe(true);
});

it('shows settings destinations without requesting unrelated account statistics', async () => {
  useAuthStore().account!.permissions = ['settings.manage'];
  const { wrapper } = await view();
  expect(wrapper.findAll('.destination').map(a => a.attributes('href'))).toEqual(['/admin/settings']);
  expect(client.summary).not.toHaveBeenCalled();
});


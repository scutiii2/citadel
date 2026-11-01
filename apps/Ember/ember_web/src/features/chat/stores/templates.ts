import { defineStore } from "pinia";
import { isApiStatus } from "../../../api/http";
import { templatesClient, type PromptTemplate } from "../api/TemplatesClient";
import { useAccountList } from "../composables/useAccountList";

/** The account's saved prompts. Loaded on first use (not at login: most
 * sessions never open the picker) and dropped when the user changes. The
 * create / update / remove actions throw ember_api's error message so the
 * dialog that called them can show it. */
export const useTemplatesStore = defineStore("templates", () => {
  const { items: templates, loading, loadError, generation, ensureLoaded, reload } = useAccountList(() => templatesClient.list());

  /** Newest edit first, as ember_api lists them. */
  function upsert(template: PromptTemplate): void {
    templates.value = [template, ...templates.value.filter((t) => t.id !== template.id)];
  }

  async function create(name: string, body: string): Promise<PromptTemplate> {
    const started = generation();
    const template = await templatesClient.create(name, body);
    if (started === generation()) upsert(template);
    return template;
  }

  async function update(id: string, name: string, body: string): Promise<PromptTemplate> {
    const started = generation();
    const template = await templatesClient.update(id, name, body);
    if (started === generation()) upsert(template);
    return template;
  }

  async function remove(id: string): Promise<void> {
    const started = generation();
    try {
      await templatesClient.remove(id);
    } catch (err) {
      // Already gone (another tab): the list should agree with the server.
      if (!isApiStatus(err, 404)) throw err;
    }
    if (started === generation()) templates.value = templates.value.filter((t) => t.id !== id);
  }

  return { templates, loading, loadError, ensureLoaded, reload, create, update, remove };
});

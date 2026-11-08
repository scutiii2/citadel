import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import { defineComponent, h, onUnmounted } from 'vue';
import WorkspaceLayout from './WorkspaceLayout.vue';

describe('WorkspaceLayout', () => {
  it('keeps panes as direct children and forwards feature classes and accessibility attributes', () => {
    const wrapper = mount(WorkspaceLayout, {
      attrs: { class: 'brain-workspace', 'aria-busy': 'true' },
      slots: { default: '<aside>Browser</aside><section>Reader</section>' },
    });
    expect(wrapper.element.tagName).toBe('DIV');
    expect(wrapper.classes()).toContain('brain-workspace');
    expect(wrapper.attributes('aria-busy')).toBe('true');
    expect(Array.from(wrapper.get('.workspace-layout').element.children).map(child => child.tagName)).toEqual(['ASIDE', 'SECTION']);
  });

  it('preserves native form submission for workspaces such as Generator', async () => {
    const submit = vi.fn();
    const wrapper = mount(WorkspaceLayout, {
      props: { as: 'form', mobile: 'stack' },
      attrs: { onSubmit: submit },
      slots: { default: '<button type="submit">Generate</button>' },
    });
    expect(wrapper.element.tagName).toBe('FORM');
    await wrapper.trigger('submit');
    expect(submit).toHaveBeenCalledOnce();
  });

  it('keeps draft-bearing panes mounted when changing mobile presentation', async () => {
    const unmounted = vi.fn();
    const Pane = defineComponent({
      setup() {
        onUnmounted(unmounted);
        return () => h('textarea');
      },
    });
    const wrapper = mount(WorkspaceLayout, { slots: { default: Pane } });
    const textarea = wrapper.get('textarea');
    await textarea.setValue('Unsaved draft');
    await wrapper.setProps({ mobile: 'stack' });
    expect(wrapper.classes()).toContain('workspace-layout--stack');
    expect(wrapper.get('textarea').element).toBe(textarea.element);
    expect(wrapper.get('textarea').element.value).toBe('Unsaved draft');
    expect(unmounted).not.toHaveBeenCalled();
  });
});

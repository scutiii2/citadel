import { expect, it, vi } from 'vitest';
import { AscensionClient } from './AscensionClient';
import type { HttpClient } from './http';

it('sends only expedition choices and retains the retry key', async () => {
  const request = vi.fn();
  const client = new AscensionClient({ request } as unknown as HttpClient);
  await client.startExpedition('guardian', 4, 'retry');
  expect(request).toHaveBeenCalledWith('POST', '/ascension/expeditions', { ascended_id: 'guardian', duration_hours: 4 }, { 'Idempotency-Key': 'retry' });
});

it('keeps Hunt selection separate from battle control mode', async () => {
  const request = vi.fn();
  const client = new AscensionClient({ request } as unknown as HttpClient);
  await client.rollEncounter('retry', 'frontier');
  expect(request).toHaveBeenCalledWith('POST', '/ascension/encounters', { difficulty_id: 'frontier' }, { 'Idempotency-Key': 'retry' });
});

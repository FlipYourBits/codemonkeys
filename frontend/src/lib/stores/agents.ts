import { writable } from 'svelte/store';
import type { AgentMeta } from '$lib/types';

export const agents = writable<AgentMeta[]>([]);

export async function fetchAgents(): Promise<void> {
  const resp = await fetch('/api/agents');
  const data: AgentMeta[] = await resp.json();
  agents.set(data);
}

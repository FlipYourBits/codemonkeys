import { writable, derived } from 'svelte/store';
import type { RunState, AgentEvent } from '$lib/types';
import { lastEvent } from './ws';

export const runs = writable<Map<string, RunState>>(new Map());
export const selectedRunId = writable<string | null>(null);

export const selectedRun = derived(
  [runs, selectedRunId],
  ([$runs, $selectedRunId]) => ($selectedRunId ? $runs.get($selectedRunId) ?? null : null),
);

export const sessionCost = derived(runs, ($runs) => {
  let total = 0;
  for (const run of $runs.values()) {
    total += run.cost_usd;
  }
  return total;
});

export const runsByStatus = derived(runs, ($runs) => {
  const running: RunState[] = [];
  const queued: RunState[] = [];
  const completed: RunState[] = [];

  for (const run of $runs.values()) {
    if (run.status === 'running') running.push(run);
    else if (run.status === 'queued') queued.push(run);
    else completed.push(run);
  }

  return { running, queued, completed };
});

lastEvent.subscribe((event) => {
  if (!event) return;

  runs.update(($runs) => {
    const run = $runs.get(event.run_id);
    if (!run) return $runs;

    run.events.push(event);

    if (event.event_type === 'TokenUpdate') {
      const data = event.data as Record<string, unknown>;
      const usage = data.usage as Record<string, number> | undefined;
      if (usage) {
        run.tokens = { input: usage.input_tokens ?? 0, output: usage.output_tokens ?? 0 };
      }
      run.cost_usd = (data.cost_usd as number) ?? run.cost_usd;
    } else if (event.event_type === 'ToolCall') {
      const data = event.data as Record<string, unknown>;
      const toolName = data.tool_name as string;
      const toolInput = data.tool_input as Record<string, unknown>;
      let detail = toolName;
      if (['Read', 'Edit', 'Write'].includes(toolName)) {
        detail = `${toolName}(${toolInput?.file_path ?? '?'})`;
      } else if (toolName === 'Grep') {
        detail = `Grep('${toolInput?.pattern ?? '?'}')`;
      } else if (toolName === 'Bash') {
        const cmd = (toolInput?.command as string) ?? '';
        detail = `Bash($ ${cmd.slice(0, 60)})`;
      }
      run.current_tool = detail;
    } else if (event.event_type === 'AgentCompleted') {
      run.status = 'completed';
      run.current_tool = null;
      const data = event.data as Record<string, unknown>;
      const result = data.result as Record<string, unknown> | undefined;
      if (result) {
        run.cost_usd = (result.cost_usd as number) ?? run.cost_usd;
        run.result = result;
      }
    } else if (event.event_type === 'AgentError') {
      run.status = 'error';
      run.current_tool = null;
    }

    return new Map($runs);
  });
});

export async function submitRun(agent: string, input: Record<string, unknown>): Promise<string> {
  const resp = await fetch('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent, input }),
  });
  const data = await resp.json();

  runs.update(($runs) => {
    $runs.set(data.run_id, {
      run_id: data.run_id,
      agent_name: agent,
      model: '',
      status: 'queued',
      cost_usd: 0,
      tokens: { input: 0, output: 0 },
      current_tool: null,
      events: [],
      result: null,
      started_at: null,
      completed_at: null,
    });
    return new Map($runs);
  });

  return data.run_id;
}

export async function cancelRun(runId: string): Promise<void> {
  await fetch(`/api/runs/${runId}`, { method: 'DELETE' });
  runs.update(($runs) => {
    const run = $runs.get(runId);
    if (run) run.status = 'cancelled';
    return new Map($runs);
  });
}

export async function killAll(): Promise<void> {
  await fetch('/api/runs', { method: 'DELETE' });
  runs.update(($runs) => {
    for (const run of $runs.values()) {
      if (run.status === 'running' || run.status === 'queued') {
        run.status = 'cancelled';
      }
    }
    return new Map($runs);
  });
}

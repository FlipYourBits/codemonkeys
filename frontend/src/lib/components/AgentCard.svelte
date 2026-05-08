<script lang="ts">
  import type { RunState } from '$lib/types';
  import { selectedRunId } from '$lib/stores/runs';
  import EventLog from './EventLog.svelte';

  interface Props {
    run: RunState;
  }

  let { run }: Props = $props();
  let expanded = $derived($selectedRunId === run.run_id);
  let agentName = $derived(run.agent_name.split(':')[0]);
  let agentFiles = $derived(run.agent_name.includes(':') ? run.agent_name.split(':').slice(1).join(':') : null);

  function handleClick() {
    selectedRunId.update((current) => (current === run.run_id ? null : run.run_id));
  }

  function statusClass(status: string): string {
    return `status-${status}`;
  }

  function formatTokens(n: number): string {
    return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
  }

  function formatCost(cost: number): string {
    return `$${cost.toFixed(cost < 0.01 ? 4 : 3)}`;
  }

  function formatDuration(run: RunState): string {
    if (!run.started_at || !run.completed_at) return '';
    const secs = run.completed_at - run.started_at;
    return secs >= 60 ? `${(secs / 60).toFixed(1)}m` : `${secs.toFixed(1)}s`;
  }

  function findingCount(run: RunState): number | null {
    if (run.status !== 'completed' || !run.result) return null;
    const result = run.result as Record<string, unknown>;
    const output = result.output as Record<string, unknown> | undefined;
    if (!output) return null;
    const results = output.results as unknown[] | undefined;
    return results?.length ?? null;
  }
</script>

<div
  class="card {statusClass(run.status)}"
  class:expanded
>
  <div
    class="card-header"
    onclick={handleClick}
    role="button"
    tabindex="0"
    onkeydown={(e) => e.key === 'Enter' && handleClick()}
  >
    <div class="left">
      <div class="status-dot"></div>
      <span class="agent-name">{agentName}</span>
      {#if agentFiles}
        <span class="agent-files" title={agentFiles}>{agentFiles}</span>
      {/if}
      <span class="model-badge">{run.model}</span>
      {#if run.status === 'queued'}
        <span class="queue-label">queued</span>
      {/if}
      {#if expanded}
        <span class="expand-indicator">▾ expanded</span>
      {/if}
    </div>
    <div class="right">
      {#if run.status === 'completed'}
        <span class="duration">{formatDuration(run)}</span>
      {/if}
      <span class="cost">{formatCost(run.cost_usd)}</span>
    </div>
  </div>

  {#if run.status === 'running' || run.status === 'completed'}
    <div class="card-meta">
      <span class="tokens">⚡ {formatTokens(run.tokens.input)} in / {formatTokens(run.tokens.output)} out</span>
      {#if run.status === 'running' && run.current_tool}
        <span class="current-tool">{run.current_tool}</span>
      {/if}
      {#if run.status === 'completed'}
        {#if findingCount(run) !== null}
          <span class="findings">{findingCount(run)} findings</span>
        {/if}
      {/if}
    </div>
  {/if}

  {#if run.status === 'error'}
    <div class="error-msg">
      {(run.result as string) ?? 'Unknown error'}
    </div>
  {/if}

  {#if expanded}
    <EventLog events={run.events} startedAt={run.started_at} />
  {/if}
</div>

<style>
  .card {
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 10px;
    transition: border-color 0.15s;
  }
  .card:hover { border-color: var(--accent); }
  .card.expanded { border-width: 2px; }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 16px;
    cursor: pointer;
  }
  .left { display: flex; align-items: center; gap: 10px; }
  .right { display: flex; align-items: center; gap: 16px; }

  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--border);
  }
  .status-running .status-dot { background: var(--accent); animation: pulse 1.5s infinite; }
  .status-queued .status-dot { background: transparent; border: 2px solid var(--text-dim); }
  .status-completed .status-dot { background: var(--green); }
  .status-error .status-dot { background: var(--red); }
  .status-cancelled .status-dot { background: var(--text-dim); }

  .status-running { border-color: var(--accent); background: rgba(129, 140, 248, 0.06); }
  .status-error { border-color: var(--red); background: rgba(239, 68, 68, 0.04); }
  .status-queued { opacity: 0.6; }

  .agent-name { font-weight: 600; font-size: 14px; }
  .agent-files {
    font-size: 11px;
    color: var(--text-dim);
    font-family: monospace;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .model-badge {
    font-size: 11px;
    color: var(--text-dim);
    border: 1px solid var(--border);
    padding: 1px 6px;
    border-radius: 3px;
  }
  .queue-label { font-size: 11px; color: var(--text-dim); margin-left: auto; }
  .expand-indicator { font-size: 11px; color: var(--accent); }

  .duration { font-size: 12px; color: var(--text-dim); }
  .cost { font-size: 13px; font-weight: 600; color: var(--green); }

  .card-meta {
    display: flex;
    justify-content: space-between;
    padding: 0 16px 12px;
    font-size: 12px;
    color: var(--text-dim);
  }
  .current-tool { font-family: monospace; color: var(--yellow); }
  .findings { color: var(--orange); }
  .error-msg { padding: 0 16px 12px; font-size: 12px; color: var(--red); }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
</style>

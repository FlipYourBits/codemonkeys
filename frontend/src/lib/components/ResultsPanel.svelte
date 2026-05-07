<script lang="ts">
  import type { Finding } from '$lib/types';
  import { selectedRun } from '$lib/stores/runs';
  import { addFindings } from '$lib/stores/queue';
  import { queue } from '$lib/stores/queue';
  import FindingsList from './FindingsList.svelte';
  import FixerQueue from './FixerQueue.svelte';

  let activeTab = $state<'results' | 'queue'>('results');
  let checkedIndices = $state(new Set<number>());

  function getFindings(): Finding[] {
    if (!$selectedRun?.result) return [];
    const result = $selectedRun.result as Record<string, unknown>;
    const output = result.output as Record<string, unknown> | undefined;
    if (!output?.results) return [];
    return output.results as Finding[];
  }

  const findings = $derived(getFindings());

  function toggleFinding(index: number) {
    checkedIndices = new Set(checkedIndices);
    if (checkedIndices.has(index)) {
      checkedIndices.delete(index);
    } else {
      checkedIndices.add(index);
    }
  }

  function handleAddToQueue() {
    if (!$selectedRun) return;
    const selected = findings.filter((_, i) => checkedIndices.has(i));
    addFindings(selected, $selectedRun.agent_name, $selectedRun.run_id);
    checkedIndices = new Set();
    activeTab = 'queue';
  }

  function exportFindings() {
    const blob = new Blob([JSON.stringify(findings, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'findings.json';
    a.click();
    URL.revokeObjectURL(url);
  }
</script>

<div class="results-panel">
  <div class="tabs">
    <button class="tab" class:active={activeTab === 'results'} onclick={() => activeTab = 'results'}>
      Results
    </button>
    <button class="tab" class:active={activeTab === 'queue'} onclick={() => activeTab = 'queue'}>
      Fixer Queue
      {#if $queue.length > 0}
        <span class="queue-badge">{$queue.length}</span>
      {/if}
    </button>
  </div>

  {#if activeTab === 'results'}
    <div class="results-content">
      {#if $selectedRun}
        <div class="results-header">
          <span class="agent-label">{$selectedRun.agent_name}</span>
          {#if $selectedRun.status === 'running'}
            <span class="streaming">streaming...</span>
          {/if}
        </div>

        {#if findings.length > 0}
          <div class="findings-list">
            <FindingsList {findings} {checkedIndices} onToggle={toggleFinding} />
          </div>

          <div class="results-actions">
            <button class="add-btn" onclick={handleAddToQueue} disabled={checkedIndices.size === 0}>
              Add to Queue ({checkedIndices.size})
            </button>
            <button class="export-btn" onclick={exportFindings}>Export</button>
          </div>
        {:else if $selectedRun.status === 'completed'}
          <div class="empty">No findings.</div>
        {:else}
          <div class="empty">Results will appear as the agent completes analysis...</div>
        {/if}
      {:else}
        <div class="empty">Click an agent card to view its results.</div>
      {/if}
    </div>
  {:else}
    <FixerQueue />
  {/if}
</div>

<style>
  .results-panel { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .tabs { display: flex; border-bottom: 1px solid var(--border); background: var(--bg-raised); }
  .tab {
    flex: 1;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 600;
    text-align: center;
    background: none;
    border: none;
    color: var(--text-dim);
    border-bottom: 2px solid transparent;
  }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab.active:last-child { color: var(--orange); border-bottom-color: var(--orange); }
  .queue-badge {
    background: var(--orange);
    color: white;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    margin-left: 4px;
  }
  .results-content { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
  .results-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    background: rgba(129, 140, 248, 0.06);
  }
  .agent-label { font-size: 12px; font-weight: 600; }
  .streaming { font-size: 11px; color: var(--text-dim); }
  .findings-list { flex: 1; overflow-y: auto; padding: 12px; }
  .results-actions {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    background: var(--bg-raised);
  }
  .add-btn {
    flex: 1;
    background: var(--orange);
    color: white;
    border: none;
    padding: 8px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
  }
  .add-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .export-btn {
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border);
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
  }
  .empty { text-align: center; padding: 40px 20px; color: var(--text-dim); font-size: 12px; }
</style>

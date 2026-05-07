<script lang="ts">
  import {
    queue, selectedCount, severityCounts,
    removeItem, toggleItem, selectAll, clearQueue, getSelectedItems,
  } from '$lib/stores/queue';
  import { submitRun } from '$lib/stores/runs';

  function severityColor(severity: string): string {
    const colors: Record<string, string> = {
      high: 'var(--red)', medium: 'var(--yellow)', low: 'var(--blue)', info: 'var(--text-dim)',
    };
    return colors[severity] ?? 'var(--text-dim)';
  }

  async function handleFix() {
    const items = getSelectedItems();
    if (items.length === 0) return;
    const findings = items.map(({ source_agent, source_run_id, selected, ...f }) => f);
    await submitRun('make_fixer', { findings });
  }

  function exportJson() {
    const items = getSelectedItems();
    const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'findings.json';
    a.click();
    URL.revokeObjectURL(url);
  }
</script>

<div class="fixer-queue">
  <div class="status-bar">
    <span class="count">{$queue.length} items queued</span>
    <div class="severity-badges">
      {#if $severityCounts.high > 0}
        <span class="badge" style="color: var(--red)">{$severityCounts.high} high</span>
      {/if}
      {#if $severityCounts.medium > 0}
        <span class="badge" style="color: var(--yellow)">{$severityCounts.medium} med</span>
      {/if}
      {#if $severityCounts.low > 0}
        <span class="badge" style="color: var(--blue)">{$severityCounts.low} low</span>
      {/if}
    </div>
  </div>

  <div class="items">
    {#each $queue as item, i (i)}
      <div class="item" style="border-left: 3px solid {severityColor(item.severity)}">
        <div class="item-header">
          <div class="left">
            <span
              class="checkbox"
              onclick={() => toggleItem(i)}
              role="checkbox"
              aria-checked={item.selected}
              tabindex="0"
              onkeydown={(e) => e.key === ' ' && toggleItem(i)}
            >
              {item.selected ? '☑' : '☐'}
            </span>
            <div>
              <div class="title">{item.title}</div>
              <div class="location">{item.file}{item.line ? `:${item.line}` : ''}</div>
            </div>
          </div>
          <button class="remove" onclick={() => removeItem(i)}>×</button>
        </div>
      </div>
    {/each}

    {#if $queue.length === 0}
      <div class="empty">No items in queue. Select findings from the Results tab and add them here.</div>
    {/if}
  </div>

  <div class="actions">
    <button class="fix-btn" onclick={handleFix} disabled={$selectedCount === 0}>
      🔧 Fix Selected ({$selectedCount})
    </button>
    <div class="secondary-actions">
      <button onclick={selectAll}>Select All</button>
      <button onclick={clearQueue}>Clear Queue</button>
      <button onclick={exportJson}>Export JSON</button>
    </div>
  </div>
</div>

<style>
  .fixer-queue { display: flex; flex-direction: column; height: 100%; }
  .status-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    background: rgba(249, 115, 22, 0.06);
  }
  .count { font-size: 12px; font-weight: 600; color: var(--orange); }
  .severity-badges { display: flex; gap: 6px; }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,0.05); }
  .items { flex: 1; overflow-y: auto; padding: 12px; }
  .item {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
  }
  .item-header { display: flex; justify-content: space-between; align-items: start; }
  .left { display: flex; gap: 8px; align-items: start; }
  .checkbox { cursor: pointer; font-size: 14px; color: var(--text-dim); }
  .checkbox[aria-checked='true'] { color: var(--green); }
  .title { font-size: 13px; font-weight: 600; }
  .location { font-size: 11px; color: var(--text-dim); font-family: monospace; margin-top: 2px; }
  .remove { background: none; border: none; color: var(--text-dim); font-size: 14px; padding: 0 4px; }
  .remove:hover { color: var(--red); }
  .empty { text-align: center; padding: 30px; color: var(--text-dim); font-size: 12px; }
  .actions { padding: 12px 16px; border-top: 1px solid var(--border); background: var(--bg-raised); }
  .fix-btn {
    width: 100%;
    background: var(--orange);
    color: white;
    border: none;
    padding: 10px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 8px;
  }
  .fix-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .secondary-actions { display: flex; gap: 8px; }
  .secondary-actions button {
    flex: 1;
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border);
    padding: 6px;
    border-radius: 6px;
    font-size: 11px;
  }
</style>

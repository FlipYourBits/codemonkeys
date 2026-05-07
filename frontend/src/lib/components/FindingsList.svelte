<script lang="ts">
  import type { Finding } from '$lib/types';

  interface Props {
    findings: Finding[];
    checkedIndices: Set<number>;
    onToggle: (index: number) => void;
  }

  let { findings, checkedIndices, onToggle }: Props = $props();

  function severityColor(severity: string): string {
    const colors: Record<string, string> = {
      high: 'var(--red)', medium: 'var(--yellow)', low: 'var(--blue)', info: 'var(--text-dim)',
    };
    return colors[severity] ?? 'var(--text-dim)';
  }
</script>

{#each findings as finding, i}
  <div class="finding">
    <div class="finding-header">
      <div class="left">
        <span
          class="checkbox"
          onclick={() => onToggle(i)}
          role="checkbox"
          aria-checked={checkedIndices.has(i)}
          tabindex="0"
          onkeydown={(e) => e.key === ' ' && onToggle(i)}
        >
          {checkedIndices.has(i) ? '☑' : '☐'}
        </span>
        <div>
          <div class="title">{finding.title}</div>
          <div class="location">{finding.file}{finding.line ? `:${finding.line}` : ''}</div>
        </div>
      </div>
      <span class="severity" style="color: {severityColor(finding.severity)}; border-color: {severityColor(finding.severity)}">
        {finding.severity}
      </span>
    </div>
    {#if finding.description}
      <div class="description">{finding.description}</div>
    {/if}
  </div>
{/each}

<style>
  .finding {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
  }
  .finding-header { display: flex; justify-content: space-between; align-items: start; }
  .left { display: flex; gap: 8px; align-items: start; }
  .checkbox { cursor: pointer; font-size: 14px; color: var(--text-dim); margin-top: 1px; }
  .checkbox[aria-checked='true'] { color: var(--green); }
  .title { font-size: 13px; font-weight: 600; }
  .location { font-size: 11px; color: var(--text-dim); font-family: monospace; margin-top: 2px; }
  .severity {
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.05);
  }
  .description { font-size: 12px; color: var(--text-dim); margin-top: 8px; line-height: 1.5; }
</style>

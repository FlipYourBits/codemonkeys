<script lang="ts">
  import { runsByStatus } from '$lib/stores/runs';
  import AgentLauncher from './AgentLauncher.svelte';
  import AgentCard from './AgentCard.svelte';
</script>

<div class="monitor">
  <AgentLauncher />

  <div class="cards">
    {#if $runsByStatus.running.length > 0}
      <div class="section-label">RUNNING</div>
      {#each $runsByStatus.running as run (run.run_id)}
        <AgentCard {run} />
      {/each}
    {/if}

    {#if $runsByStatus.queued.length > 0}
      <div class="section-label">QUEUED</div>
      {#each $runsByStatus.queued as run (run.run_id)}
        <AgentCard {run} />
      {/each}
    {/if}

    {#if $runsByStatus.completed.length > 0}
      <div class="section-label">COMPLETED</div>
      {#each $runsByStatus.completed as run (run.run_id)}
        <AgentCard {run} />
      {/each}
    {/if}

    {#if $runsByStatus.running.length === 0 && $runsByStatus.queued.length === 0 && $runsByStatus.completed.length === 0}
      <div class="empty">
        <p>No agent runs yet.</p>
        <p class="hint">Select files on the left, pick an agent, and click Run.</p>
      </div>
    {/if}
  </div>
</div>

<style>
  .monitor { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .cards { flex: 1; overflow-y: auto; padding: 16px; }
  .section-label {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 12px;
    margin-top: 8px;
  }
  .section-label:first-child { margin-top: 0; }
  .empty { text-align: center; padding: 60px 20px; color: var(--text-dim); }
  .hint { font-size: 12px; margin-top: 8px; }
</style>

<script lang="ts">
  import { agents } from '$lib/stores/agents';
  import { selectedFiles } from '$lib/stores/files';
  import { submitRun, killAll } from '$lib/stores/runs';

  let selectedAgent = $state('');

  $effect(() => {
    if ($agents.length > 0 && !selectedAgent) {
      selectedAgent = $agents[0].name;
    }
  });

  async function handleRun() {
    if (!selectedAgent || $selectedFiles.length === 0) return;
    await submitRun(selectedAgent, { files: $selectedFiles });
  }

  async function handleKillAll() {
    await killAll();
  }
</script>

<div class="launcher">
  <select bind:value={selectedAgent}>
    {#each $agents as agent}
      <option value={agent.name}>{agent.name}</option>
    {/each}
  </select>

  <button class="run-btn" onclick={handleRun} disabled={$selectedFiles.length === 0}>
    ▶ Run
  </button>

  <div class="divider"></div>

  <button class="kill-btn" onclick={handleKillAll}>
    Kill All
  </button>
</div>

<style>
  .launcher {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-raised);
  }
  select {
    flex: 1;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
  }
  .run-btn {
    background: var(--accent);
    color: white;
    border: none;
    padding: 6px 20px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 13px;
  }
  .run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .divider { width: 1px; height: 24px; background: var(--border); }
  .kill-btn {
    background: transparent;
    color: var(--red);
    border: 1px solid var(--red);
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12px;
  }
  .kill-btn:hover { background: rgba(239, 68, 68, 0.1); }
</style>

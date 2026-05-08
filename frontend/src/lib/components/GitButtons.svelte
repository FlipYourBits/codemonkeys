<script lang="ts">
  import { fetchGitFiles, clearSelection } from '$lib/stores/files';

  let activeMode = $state('');

  async function selectMode(mode: string) {
    if (activeMode === mode) {
      activeMode = '';
      clearSelection();
      return;
    }
    activeMode = mode;
    await fetchGitFiles(mode);
  }
</script>

<div class="git-buttons">
  <button class:active={activeMode === 'changed'} onclick={() => selectMode('changed')}>Changed</button>
  <button class:active={activeMode === 'staged'} onclick={() => selectMode('staged')}>Staged</button>
  <button class:active={activeMode === 'all-py'} onclick={() => selectMode('all-py')}>All .py</button>
</div>

<style>
  .git-buttons { display: flex; gap: 6px; margin-bottom: 10px; }
  button {
    padding: 4px 10px;
    font-size: 11px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-dim);
  }
  button:hover { border-color: var(--accent); color: var(--text); }
  button.active { background: var(--accent); color: white; border-color: var(--accent); }
</style>

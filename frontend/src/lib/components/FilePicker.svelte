<script lang="ts">
  import { fileTree, selectedFiles, searchQuery, fetchTree } from '$lib/stores/files';
  import FileTree from './FileTree.svelte';
  import GitButtons from './GitButtons.svelte';
  import DropZone from './DropZone.svelte';
  import { onMount } from 'svelte';

  onMount(() => {
    fetchTree();
  });
</script>

<div class="picker">
  <div class="header">
    <div class="title">FILES</div>
    <GitButtons />
    <input
      class="search"
      type="text"
      placeholder="Search files..."
      bind:value={$searchQuery}
    />
  </div>

  <div class="tree">
    <FileTree nodes={$fileTree} />
  </div>

  <div class="footer">
    <div class="count">{$selectedFiles.length} files selected</div>
    <DropZone />
  </div>
</div>

<style>
  .picker { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-raised);
  }
  .title { font-weight: 600; font-size: 13px; margin-bottom: 10px; }
  .search {
    width: 100%;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
    margin-top: 10px;
  }
  .search::placeholder { color: var(--text-dim); }
  .tree { flex: 1; overflow-y: auto; padding: 12px 16px; }
  .footer {
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    background: var(--bg-raised);
  }
  .count { font-size: 12px; color: var(--text-dim); margin-bottom: 8px; }
</style>

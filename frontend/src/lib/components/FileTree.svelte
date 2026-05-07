<script lang="ts">
  import type { FileNode } from '$lib/types';
  import { toggleNode, toggleExpand, searchQuery } from '$lib/stores/files';

  interface Props {
    nodes: FileNode[];
    depth?: number;
  }

  let { nodes, depth = 0 }: Props = $props();

  function matchesSearch(node: FileNode, query: string): boolean {
    if (!query) return true;
    const q = query.toLowerCase();
    if (node.name.toLowerCase().includes(q)) return true;
    if (node.children) return node.children.some((c) => matchesSearch(c, q));
    return false;
  }

  const filteredNodes = $derived(
    nodes
      .filter((n) => matchesSearch(n, $searchQuery))
      .sort((a, b) => {
        if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
        return a.name.localeCompare(b.name);
      })
  );
</script>

{#each filteredNodes as node (node.path)}
  <div class="tree-node" style="padding-left: {depth * 16}px">
    <span
      class="checkbox"
      onclick={(e) => { e.stopPropagation(); toggleNode(node.path); }}
      role="checkbox"
      aria-checked={node.selected}
      tabindex="0"
      onkeydown={(e) => e.key === ' ' && toggleNode(node.path)}
    >
      {node.selected ? '☑' : '☐'}
    </span>

    {#if node.is_dir}
      <span
        class="folder"
        onclick={() => toggleExpand(node.path)}
        role="button"
        tabindex="0"
        onkeydown={(e) => e.key === 'Enter' && toggleExpand(node.path)}
      >
        {node.expanded ? '📂' : '📁'} {node.name}/
      </span>
    {:else}
      <span class="file">{node.name}</span>
    {/if}
  </div>

  {#if node.is_dir && node.expanded && node.children}
    <svelte:self nodes={node.children} depth={depth + 1} />
  {/if}
{/each}

<style>
  .tree-node {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 0;
    font-size: 13px;
    line-height: 1.8;
  }
  .checkbox {
    cursor: pointer;
    user-select: none;
    color: var(--text-dim);
  }
  .checkbox[aria-checked='true'] { color: var(--green); }
  .folder { cursor: pointer; color: var(--accent); }
  .file { color: var(--text); }
</style>

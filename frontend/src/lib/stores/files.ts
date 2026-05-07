import { writable, derived } from 'svelte/store';
import type { FileNode } from '$lib/types';

export const fileTree = writable<FileNode[]>([]);
export const searchQuery = writable('');

export const selectedFiles = derived(fileTree, ($tree) => {
  const selected: string[] = [];
  function walk(nodes: FileNode[]) {
    for (const node of nodes) {
      if (node.selected && !node.is_dir) {
        selected.push(node.path);
      }
      if (node.children) walk(node.children);
    }
  }
  walk($tree);
  return selected;
});

export function buildTreeFromPaths(paths: string[]): FileNode[] {
  const nodeMap = new Map<string, FileNode>();

  for (const path of paths) {
    const parts = path.split('/');

    for (let i = 0; i < parts.length; i++) {
      const fullPath = parts.slice(0, i + 1).join('/');
      const isLast = i === parts.length - 1;

      if (!nodeMap.has(fullPath)) {
        nodeMap.set(fullPath, {
          name: parts[i],
          path: fullPath,
          is_dir: !isLast,
          children: isLast ? undefined : [],
          selected: false,
          expanded: false,
        });
      }

      if (i > 0) {
        const parentPath = parts.slice(0, i).join('/');
        const parent = nodeMap.get(parentPath);
        const child = nodeMap.get(fullPath)!;
        if (parent && parent.children && !parent.children.includes(child)) {
          parent.children.push(child);
        }
      }
    }
  }

  const roots: FileNode[] = [];
  for (const [path, node] of nodeMap) {
    if (!path.includes('/')) {
      roots.push(node);
    }
  }

  return roots.sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

export async function fetchTree(): Promise<void> {
  const resp = await fetch('/api/files/tree');
  const paths: string[] = await resp.json();
  fileTree.set(buildTreeFromPaths(paths));
}

export async function fetchGitFiles(mode: string): Promise<void> {
  const resp = await fetch(`/api/files/git/${mode}`);
  const paths: string[] = await resp.json();
  fileTree.update(($tree) => {
    function clearSelection(nodes: FileNode[]) {
      for (const node of nodes) {
        node.selected = false;
        if (node.children) clearSelection(node.children);
      }
    }
    clearSelection($tree);

    const pathSet = new Set(paths);
    function selectMatches(nodes: FileNode[]) {
      for (const node of nodes) {
        if (pathSet.has(node.path)) node.selected = true;
        if (node.children) selectMatches(node.children);
      }
    }
    selectMatches($tree);
    return [...$tree];
  });
}

export function toggleNode(path: string): void {
  fileTree.update(($tree) => {
    function walk(nodes: FileNode[]) {
      for (const node of nodes) {
        if (node.path === path) {
          node.selected = !node.selected;
          if (node.is_dir && node.children) {
            function setAll(nodes: FileNode[], val: boolean) {
              for (const n of nodes) {
                n.selected = val;
                if (n.children) setAll(n.children, val);
              }
            }
            setAll(node.children, node.selected);
          }
          return;
        }
        if (node.children) walk(node.children);
      }
    }
    walk($tree);
    return [...$tree];
  });
}

export function toggleExpand(path: string): void {
  fileTree.update(($tree) => {
    function walk(nodes: FileNode[]) {
      for (const node of nodes) {
        if (node.path === path) {
          node.expanded = !node.expanded;
          return;
        }
        if (node.children) walk(node.children);
      }
    }
    walk($tree);
    return [...$tree];
  });
}

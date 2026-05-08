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

export function clearSelection(): void {
  fileTree.update(($tree) => {
    function update(nodes: FileNode[]): FileNode[] {
      return nodes.map((node) => ({
        ...node,
        selected: false,
        children: node.children ? update(node.children) : undefined,
      }));
    }
    return update($tree);
  });
}

export async function fetchGitFiles(mode: string): Promise<void> {
  const resp = await fetch(`/api/files/git/${mode}`);
  const paths: string[] = await resp.json();
  const pathSet = new Set(paths);

  const parentDirs = new Set<string>();
  for (const p of paths) {
    const parts = p.split('/');
    for (let i = 1; i < parts.length; i++) {
      parentDirs.add(parts.slice(0, i).join('/'));
    }
  }

  fileTree.update(($tree) => {
    function update(nodes: FileNode[]): FileNode[] {
      return nodes.map((node) => {
        const selected = pathSet.has(node.path);
        const expanded = parentDirs.has(node.path) ? true : node.expanded;
        const children = node.children ? update(node.children) : undefined;
        return { ...node, selected, expanded, children };
      });
    }
    return update($tree);
  });
}

export function toggleNode(path: string): void {
  fileTree.update(($tree) => {
    function update(nodes: FileNode[]): FileNode[] {
      return nodes.map((node) => {
        if (node.path === path) {
          const newSelected = !node.selected;
          const children = node.is_dir && node.children
            ? setAll(node.children, newSelected)
            : node.children;
          return { ...node, selected: newSelected, children };
        }
        if (node.children) {
          return { ...node, children: update(node.children) };
        }
        return node;
      });
    }
    function setAll(nodes: FileNode[], val: boolean): FileNode[] {
      return nodes.map((n) => ({
        ...n,
        selected: val,
        children: n.children ? setAll(n.children, val) : undefined,
      }));
    }
    return update($tree);
  });
}

export function expandAll(): void {
  fileTree.update(($tree) => {
    function update(nodes: FileNode[]): FileNode[] {
      return nodes.map((node) => ({
        ...node,
        expanded: node.is_dir ? true : node.expanded,
        children: node.children ? update(node.children) : undefined,
      }));
    }
    return update($tree);
  });
}

export function collapseAll(): void {
  fileTree.update(($tree) => {
    function update(nodes: FileNode[]): FileNode[] {
      return nodes.map((node) => ({
        ...node,
        expanded: false,
        children: node.children ? update(node.children) : undefined,
      }));
    }
    return update($tree);
  });
}

export function toggleExpand(path: string): void {
  fileTree.update(($tree) => {
    function update(nodes: FileNode[]): FileNode[] {
      return nodes.map((node) => {
        if (node.path === path) {
          return { ...node, expanded: !node.expanded };
        }
        if (node.children) {
          return { ...node, children: update(node.children) };
        }
        return node;
      });
    }
    return update($tree);
  });
}

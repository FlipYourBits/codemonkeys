import { writable, derived } from 'svelte/store';
import type { QueueItem, Finding } from '$lib/types';

export const queue = writable<QueueItem[]>([]);

export const selectedCount = derived(queue, ($queue) =>
  $queue.filter((item) => item.selected).length,
);

export const severityCounts = derived(queue, ($queue) => ({
  high: $queue.filter((i) => i.severity === 'high').length,
  medium: $queue.filter((i) => i.severity === 'medium').length,
  low: $queue.filter((i) => i.severity === 'low').length,
  info: $queue.filter((i) => i.severity === 'info').length,
}));

export function addFindings(findings: Finding[], sourceAgent: string, sourceRunId: string): void {
  queue.update(($queue) => [
    ...$queue,
    ...findings.map((f) => ({
      ...f,
      source_agent: sourceAgent,
      source_run_id: sourceRunId,
      selected: true,
    })),
  ]);
}

export function removeItem(index: number): void {
  queue.update(($queue) => $queue.filter((_, i) => i !== index));
}

export function toggleItem(index: number): void {
  queue.update(($queue) => {
    $queue[index].selected = !$queue[index].selected;
    return [...$queue];
  });
}

export function selectAll(): void {
  queue.update(($queue) => {
    $queue.forEach((item) => (item.selected = true));
    return [...$queue];
  });
}

export function clearQueue(): void {
  queue.set([]);
}

export function getSelectedItems(): QueueItem[] {
  let items: QueueItem[] = [];
  queue.subscribe(($queue) => {
    items = $queue.filter((item) => item.selected);
  })();
  return items;
}

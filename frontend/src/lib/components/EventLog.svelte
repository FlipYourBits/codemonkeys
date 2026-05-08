<script lang="ts">
  import type { AgentEvent } from '$lib/types';

  interface Props {
    events: AgentEvent[];
    startedAt: number | null;
  }

  let { events, startedAt }: Props = $props();

  function formatTime(timestamp: number): string {
    if (!startedAt) return '00:00.0';
    const elapsed = timestamp - startedAt;
    const mins = Math.floor(elapsed / 60);
    const secs = (elapsed % 60).toFixed(1);
    return mins > 0 ? `${mins}:${secs.padStart(4, '0')}` : secs.padStart(4, '0');
  }

  function eventColor(type: string): string {
    if (type === 'ToolCall' || type === 'ToolResult') return 'var(--yellow)';
    if (type === 'ThinkingOutput') return 'var(--purple)';
    if (type === 'TextOutput') return 'var(--green)';
    if (type === 'AgentStarted') return 'var(--accent)';
    if (type === 'ToolDenied') return 'var(--red)';
    if (type === 'RateLimitHit') return 'var(--red)';
    return 'var(--text-dim)';
  }

  function eventLabel(type: string): string {
    const labels: Record<string, string> = {
      AgentStarted: 'START',
      ToolCall: 'TOOL',
      ToolResult: 'RESULT',
      ToolDenied: 'DENIED',
      ThinkingOutput: 'THINK',
      TextOutput: 'TEXT',
      TokenUpdate: 'TOKENS',
      RateLimitHit: 'RATE',
    };
    return labels[type] ?? type;
  }

  function eventDetail(event: AgentEvent): string {
    const d = event.data as Record<string, unknown>;
    if (event.event_type === 'AgentStarted') return `Agent started — model: ${d.model}`;
    if (event.event_type === 'ToolCall') {
      const name = d.tool_name as string;
      const input = d.tool_input as Record<string, unknown>;
      if (['Read', 'Edit', 'Write'].includes(name)) return `${name}(${input?.file_path ?? '?'})`;
      if (name === 'Grep') return `Grep('${input?.pattern ?? '?'}')`;
      if (name === 'Bash') return `Bash($ ${(input?.command as string) ?? ''})`;
      return name;
    }
    if (event.event_type === 'ToolResult') {
      const output = (d.output as string) ?? '';
      return `→ ${output}`;
    }
    if (event.event_type === 'ThinkingOutput') return (d.text as string) ?? '';
    if (event.event_type === 'TextOutput') return (d.text as string) ?? '';
    if (event.event_type === 'ToolDenied') return `DENIED: ${d.tool_name}(${d.command})`;
    if (event.event_type === 'RateLimitHit') return `Rate limited — waiting ${d.wait_seconds}s`;
    return '';
  }

  const hiddenTypes = ['TokenUpdate', 'RawMessage', 'AgentCompleted', 'AgentError'];

  const displayEvents = $derived(
    events.filter((e) => !hiddenTypes.includes(e.event_type))
  );

  let copied = $state(false);

  function copyLog() {
    const text = displayEvents
      .map((e) => `${formatTime(e.timestamp)} [${eventLabel(e.event_type)}] ${eventDetail(e)}`)
      .join('\n');
    navigator.clipboard.writeText(text);
    copied = true;
    setTimeout(() => { copied = false; }, 1500);
  }
</script>

<div class="event-log" onclick={(e) => e.stopPropagation()}>
  <div class="log-toolbar">
    <button class="copy-btn" onclick={copyLog}>{copied ? 'Copied!' : 'Copy log'}</button>
  </div>
  {#each displayEvents as event}
    <div class="event-line">
      <span class="time">{formatTime(event.timestamp)}</span>
      <span class="badge" style="color: {eventColor(event.event_type)}">{eventLabel(event.event_type)}</span>
      <span class="detail">{eventDetail(event)}</span>
    </div>
  {/each}
</div>

<style>
  .event-log {
    background: rgba(0, 0, 0, 0.3);
    border-top: 1px solid rgba(129, 140, 248, 0.2);
    padding: 12px 16px;
    max-height: 260px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.9;
    user-select: text;
  }
  .log-toolbar {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 4px;
  }
  .copy-btn {
    font-size: 10px;
    color: var(--text-dim);
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 2px 8px;
    cursor: pointer;
  }
  .copy-btn:hover { color: var(--text); border-color: var(--accent); }
  .event-line { display: flex; gap: 8px; align-items: baseline; }
  .time { color: var(--text-dim); min-width: 42px; flex-shrink: 0; }
  .badge { font-weight: 600; min-width: 50px; flex-shrink: 0; }
  .detail { color: var(--text-dim); word-break: break-word; white-space: pre-wrap; }
</style>

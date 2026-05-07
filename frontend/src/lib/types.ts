export type RunStatus = 'queued' | 'running' | 'completed' | 'error' | 'cancelled';
export type Severity = 'high' | 'medium' | 'low' | 'info';

export interface AgentMeta {
  name: string;
  description: string;
  accepts: string[];
  default_model: string;
}

export interface TokenUsage {
  input: number;
  output: number;
}

export interface RunState {
  run_id: string;
  agent_name: string;
  model: string;
  status: RunStatus;
  cost_usd: number;
  tokens: TokenUsage;
  current_tool: string | null;
  events: AgentEvent[];
  result: unknown | null;
  started_at: number | null;
  completed_at: number | null;
}

export interface AgentEvent {
  run_id: string;
  event_type: string;
  agent_name: string;
  data: Record<string, unknown>;
  timestamp: number;
}

export interface Finding {
  file: string;
  line: number | null;
  severity: Severity;
  category: string;
  title: string;
  description: string;
  suggestion: string | null;
}

export interface QueueItem extends Finding {
  source_agent: string;
  source_run_id: string;
  selected: boolean;
}

export interface FileNode {
  name: string;
  path: string;
  is_dir: boolean;
  children?: FileNode[];
  selected: boolean;
  expanded: boolean;
}

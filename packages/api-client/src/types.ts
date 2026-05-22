// Re-export AxiosError as the standard error type for consumers.
export { AxiosError as ApiError } from "axios";

export type * from "./types.generated";

import type {
  AgentDelivery,
  AgentExecutionStateEvent,
  AgentExecutionStatus,
  AgentInputContentBlock,
  AgentMessageEvent,
  AgentMessageRole,
  AgentStreamData,
  TextContentBlock,
} from "./types.generated";

type ApiObject = Record<string, unknown>;

export type ClientLogValue = string | number | boolean | null | ApiObject | Error;
export type ClientLogger = {
  info: (...values: ClientLogValue[]) => void;
  warn: (...values: ClientLogValue[]) => void;
  error: (...values: ClientLogValue[]) => void;
};

export type InputContentBlock = AgentInputContentBlock;

export interface SpawnOptions {
  threadKey: string;
  spawnId?: string;
  harness?: string;
  engine?: string;
  personaId?: string;
  agentsMdOverride?: string;
}

export interface MessageOptions {
  threadKey: string;
  assignmentGeneration: number;
  messageId?: string;
  role?: AgentMessageRole;
  event?: AgentMessageEvent;
  parts?: AgentInputContentBlock[];
  userId?: string;
  metadata?: ApiObject;
}

export interface ExecuteOptions {
  threadKey: string;
  assignmentGeneration: number;
  executeId?: string;
  harness?: string;
  platform?: string;
  userId?: string;
  metadata?: ApiObject;
  delivery?: AgentDelivery;
}

export interface WorkflowRunOptions {
  workflowName: string;
  triggerKey?: string;
  input?: ApiObject;
  eagerStart?: boolean;
  timeoutMs?: number;
}

export interface WorkflowRunAccepted extends ApiObject {
  ok: boolean;
  run_id: string;
  workflow_name: string;
  workflow_version?: string;
  workflow_source_path?: string | null;
  parent_run_id?: string | null;
  root_run_id?: string | null;
  status: string;
  thread_key?: string | null;
  execution_id?: string | null;
  output_json?: unknown;
  error_text?: string | null;
  latest_checkpoint_name?: string | null;
  latest_step_kind?: string | null;
  waiting_on?: ApiObject | null;
  child_runs_count?: number;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  idempotent?: boolean;
}

export interface WorkflowEventAccepted extends ApiObject {
  ok: boolean;
  event_type: string;
  correlation_id: string;
  runs_woken: number;
}

export interface ThreadMessageRecord extends ApiObject {
  id: string;
  role: AgentMessageRole | string;
  parts: AgentInputContentBlock[];
  user_id?: string | null;
  metadata?: ApiObject | null;
  created_at?: string | null;
}

export function isExecutionStateEvent(
  data: AgentStreamData,
): data is AgentExecutionStateEvent {
  return data.type === "execution.state";
}

export function resultTextFromStreamData(data: AgentStreamData): string {
  if (data.type === "execution.state" || data.type === "final_delivery.ready") {
    return typeof data.result_text === "string" ? data.result_text : "";
  }
  if (data.type === "result" || data.type === "turn.done" || data.type === "turn.completed") {
    return firstText(data.result_text, data.result, data.text);
  }
  return "";
}

export function assistantTextFromStreamData(data: AgentStreamData): string {
  if (data.type !== "assistant") return "";
  const content = data.message.content;
  if (typeof content === "string") return content;
  return content
    .filter((part): part is TextContentBlock => part.type === "text")
    .map(part => part.text)
    .filter(Boolean)
    .join("\n");
}

export function textFromStreamData(data: AgentStreamData): string {
  return resultTextFromStreamData(data) || assistantTextFromStreamData(data);
}

export function statusFromStreamData(data: AgentStreamData): AgentExecutionStatus | "" {
  return data.type === "execution.state" ? data.status : "";
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    let text = "";
    try {
      text = assertString(value).trim();
    } catch {
      continue;
    }
    if (text) return text;
  }
  return "";
}

function assertString(value: unknown): string {
  if (typeof value !== "string") throw new Error("expected string");
  return value;
}

import type {
  Engine,
  FileAttachment,
  Harness,
} from "../harness";
import { decode as decodeToon } from "@toon-format/toon";
import { apiPost } from "../api-client";
import {
  inferLegalDealProfile,
  inferLegalWorkflow,
  type KnowledgeRoutingPlan,
  runLegalPromptLoop,
  type LegalWorkflow,
} from "./legal";
import { executeWithBusyRetries } from "./common";

export type ModeExecutionParams = {
  harness: Harness;
  legalLoopEnabled: boolean;
  instruction: string;
  message: string;
  sessionEnvelope?: string;
  isLegalKickoff?: boolean;
  threadKey: string;
  requestId: string;
  files: FileAttachment[];
  userId?: string;
  model?: string | null;
  engine?: Engine | null;
  onPhaseStatus?: (phase: string) => Promise<void> | void;
};

type ModePlugin = {
  id: string;
  matches: (params: ModeExecutionParams) => boolean;
  run: (params: ModeExecutionParams) => Promise<string>;
};

function parseKnowledgeRoutingPlanResponse(
  response: Record<string, unknown>,
): KnowledgeRoutingPlan | null {
  const parseCandidate = (value: unknown): KnowledgeRoutingPlan | null => {
    if (value && typeof value === "object") {
      const obj = value as Record<string, unknown>;
      if ("lookup_dynamic" in obj || "system_evergreen_calls" in obj || "plan_hash" in obj) {
        return obj as KnowledgeRoutingPlan;
      }
      return null;
    }
    if (typeof value !== "string" || !value.trim()) {
      return null;
    }
    try {
      const parsed = JSON.parse(value);
      if (parsed && typeof parsed === "object") {
        const obj = parsed as Record<string, unknown>;
        if ("lookup_dynamic" in obj || "system_evergreen_calls" in obj || "plan_hash" in obj) {
          return obj as KnowledgeRoutingPlan;
        }
      }
    } catch {}
    try {
      const parsed = decodeToon(value, { strict: false });
      if (parsed && typeof parsed === "object") {
        const obj = parsed as Record<string, unknown>;
        if ("lookup_dynamic" in obj || "system_evergreen_calls" in obj || "plan_hash" in obj) {
          return obj as KnowledgeRoutingPlan;
        }
      }
    } catch {
      return null;
    }
    return null;
  };

  return parseCandidate(response.result) ?? parseCandidate(response);
}

const legalLoopPlugin: ModePlugin = {
  id: "legal-loop",
  matches: (params) => params.harness === "legal" && params.legalLoopEnabled,
  run: async (params) => {
    const workflow: LegalWorkflow = inferLegalWorkflow(params.instruction);
    const isKickoff = params.isLegalKickoff === true;
    const dealProfile = inferLegalDealProfile(params.instruction, workflow, params.files);
    let knowledgeRoutingPlan: KnowledgeRoutingPlan | null = null;
    if (!isKickoff) {
      try {
        const response = await apiPost(
          "/tools/legal-playbook/get_knowledge_plan",
          {
            workflow,
            phase: "retrieval",
            deal_profile: dealProfile,
            max_dynamic_packs: 2,
            max_dynamic_chars: 5000,
          },
          { timeoutMs: 3_500, maxAttempts: 1 },
        );
        knowledgeRoutingPlan = parseKnowledgeRoutingPlanResponse(response);
        if (!knowledgeRoutingPlan) {
          console.warn("legal_knowledge_plan_parse_failed", {
            thread: params.threadKey,
            requestId: params.requestId,
            workflow,
          });
        }
      } catch (error) {
        console.warn("legal_knowledge_plan_fallback", {
          thread: params.threadKey,
          requestId: params.requestId,
          workflow,
          error: error instanceof Error ? error.message : String(error),
        });
        knowledgeRoutingPlan = null;
      }
    }

    return runLegalPromptLoop({
      threadKey: params.threadKey,
      requestId: params.requestId,
      harness: params.harness,
      workflow,
      // Use the user's raw instruction for workflow heuristics.
      // `params.message` also includes injected context text.
      originalRequest: params.instruction,
      sessionEnvelope: params.sessionEnvelope,
      kickoff: isKickoff,
      files: params.files,
      userId: params.userId,
      model: params.model,
      engine: params.engine,
      knowledgeRoutingPlan,
      onPhaseStatus: params.onPhaseStatus,
    });
  },
};

const defaultPlugin: ModePlugin = {
  id: "default-single-run",
  matches: () => true,
  run: (params) =>
    executeWithBusyRetries({
      threadKey: params.threadKey,
      message: params.message,
      harness: params.harness,
      requestId: params.requestId,
      files: params.files.length > 0 ? params.files : undefined,
      userId: params.userId,
      model: params.model,
      engine: params.engine,
      legalLoopEnabled: params.legalLoopEnabled,
    }),
};

const MODE_PLUGINS: ModePlugin[] = [legalLoopPlugin, defaultPlugin];

export async function runModeExecution(params: ModeExecutionParams): Promise<string> {
  const plugin = MODE_PLUGINS.find((candidate) => candidate.matches(params));
  if (!plugin) {
    throw new Error("No mode plugin available for this execution");
  }
  console.info("mode_execution_plugin_selected", {
    plugin: plugin.id,
    thread: params.threadKey,
    harness: params.harness,
  });
  return plugin.run(params);
}

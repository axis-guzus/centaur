import { decode as decodeToon } from "@toon-format/toon";
import { apiPost } from "../api-client";
import type {
  Engine,
  FileAttachment,
  Harness,
} from "../harness";
import { executeWithBusyRetries } from "./common";

export type LegalWorkflow = "question" | "draft" | "review" | "revision" | "unknown";
type LegalPhase =
  | "intake"
  | "clarify"
  | "retrieval"
  | "authority"
  | "analysis"
  | "draft"
  | "critic"
  | "revise"
  | "compliance"
  | "finalize";

const LEGAL_MAX_REVIEW_LOOPS = 2;
const TERM_SHEET_HINT_RE =
  /\bterm sheet|post-money|pre-money|valuation|series (seed|[a-z])|protective provisions\b/i;
const TOKEN_RELEVANT_RE = /\b(token|crypto|web3|blockchain|defi|dao|warrant)\b/i;
const AI_COMPANY_RE = /\b(ai|a\.i\.|machine learning|ml|llm|foundation model)\b/i;
const MA_EXIT_RE = /\b(m&a|acquisition|sale process|exit|merger|spac|ipo|direct listing)\b/i;
const REGULATORY_RE =
  /\b(sec|cftc|ofac|regulatory|compliance|rule 506|bad actor|hsr|cfius|oisp)\b/i;
const DOC_TYPE_PATTERNS: Array<{ pattern: RegExp; docType: string }> = [
  { pattern: /\bterm sheet\b/i, docType: "term_sheet" },
  { pattern: /\bcharter|certificate of incorporation\b/i, docType: "charter" },
  { pattern: /\bspa|stock purchase agreement\b/i, docType: "spa" },
  { pattern: /\bira|investors'? rights agreement\b/i, docType: "ira" },
  { pattern: /\bvoting agreement\b/i, docType: "voting" },
  { pattern: /\brofr|co-sale\b/i, docType: "rofr" },
  { pattern: /\bmrl|management rights letter|side letter\b/i, docType: "mrl_and_side_letters" },
  { pattern: /\btoken warrant\b/i, docType: "token_warrant" },
];

export type KnowledgeRoutingPlan = Record<string, unknown>;

export function inferLegalWorkflow(instruction: string): LegalWorkflow {
  const normalized = instruction.toLowerCase();
  if (/\b(revise|revision|redline|edit|update)\b/.test(normalized)) return "revision";
  if (/\b(review|analyze|audit|compare|check)\b/.test(normalized)) return "review";
  if (/\b(draft|create|generate|prepare|write)\b/.test(normalized)) return "draft";
  if (
    normalized.includes("?") ||
    /\b(what|why|how|when|where|who|can|could|should|is|are|does|do)\b/.test(normalized)
  ) {
    return "question";
  }
  return "unknown";
}

export function inferLegalDealProfile(
  instruction: string,
  workflow: LegalWorkflow,
  files: FileAttachment[],
): Record<string, unknown> {
  const normalized = instruction.toLowerCase();
  const docType = DOC_TYPE_PATTERNS.find((entry) => entry.pattern.test(instruction))?.docType ?? "unknown";
  const seriesMatch = instruction.match(/\bseries\s+(seed|[a-z])\b/i);
  const series = seriesMatch ? seriesMatch[1].toLowerCase() : "";
  const stage =
    /\bseries\s+(g|h|i|j)\b/i.test(instruction) || /\blate[- ]stage\b/i.test(instruction)
      ? "late"
      : /\bseries\s+(c|d|e|f)\b/i.test(instruction) || /\bgrowth\b/i.test(instruction)
        ? "growth"
        : "early";
  const queryFocus = MA_EXIT_RE.test(instruction)
    ? "ma_exit"
    : REGULATORY_RE.test(instruction)
      ? "regulatory"
      : "general";
  return {
    workflow,
    document_type: docType,
    stage,
    series,
    token_relevant: TOKEN_RELEVANT_RE.test(instruction) || files.some((f) => TOKEN_RELEVANT_RE.test(f.name)),
    company_type: AI_COMPANY_RE.test(normalized) ? "ai" : "other",
    query_focus: queryFocus,
    has_attachments: files.length > 0,
  };
}

export function buildLegalKickoffInstruction(): string {
  return [
    "The user invoked `--legal` without a specific task.",
    "Respond with a concise kickoff message in lawyer-facing style.",
    "Requirements:",
    "- include this exact phrase: `I am not a lawyer; I am a legal agent created by Paradigm.`",
    "- explain what you can help with now: legal questions, doc review, drafting/revision, term sheet support",
    "- provide 4 short example prompts the lawyer can send next",
    "- ask one focused follow-up question to start work",
    "- keep output under 220 words and avoid marketing tone",
  ].join("\n");
}

export function buildLegalSessionContext(
  threadId: string,
  instruction: string,
  files: FileAttachment[],
): string {
  const now = new Date().toISOString().replace("T", " ").slice(0, 19);
  const workflow = inferLegalWorkflow(instruction);
  const attachmentNames = files.map((f) => f.name).join(", ");
  const qualityDepth = workflow === "question" ? "light" : "full";
  return [
    "# Legal Session Context",
    "",
    `- **Date/Time**: ${now} UTC`,
    `- **Thread ID**: ${threadId}`,
    `- **Workflow hint**: ${workflow}`,
    `- **Attachments**: ${attachmentNames || "none"}`,
    "",
    "## Operating Rules",
    "- You are a legal assistant, not a lawyer. State this clearly when giving legal analysis.",
    "- Surface all meaningful deviations; do not hide low-severity issues.",
    "- Draft only. Never send external communications or execute legal actions autonomously.",
    "- Economics are highest-priority issues; escalate valuation/check-size/option-pool/board-voting changes.",
    "- Keep founder relationship and execution speed in view for non-economic asks.",
    "- Apply stage-aware governance posture (early lead vs late-stage minority ownership).",
    "- Tool-call contract is strict: `call <tool> <method> <json_body>` (or `call discover <tool>`).",
    "- For shell JSON args, quote the body as one token (e.g., `'{\"document_type\":\"term_sheet\"}'`).",
    "- Prefer explicit tool names in outputs/prompts: `legal-playbook` and `termsheet`.",
    "- Canonical legal playbook tool id is exactly `legal-playbook`.",
    "- `legal-playbook` is an API tool reached through `call ...` shell commands, not a skill.",
    "- Source precedence is strict: policy rules > canonical internal financing context > executed precedents > broad market guidance.",
    "- Write in lawyer-facing style: precise, direct, low-fluff, and explicit about assumptions and risk.",
    "- Prefer concrete issue statements, defined terms, and clear recommendation language over generic advice.",
    "",
    "## Workflow Policy",
    "- QUESTION: answer directly with assumptions and uncertainty boundaries.",
    "- DRAFT/REVIEW/REVISION: run playbook checks + quality loop before final output.",
    `- Quality depth: ${qualityDepth} (question=light, all else=full).`,
    "",
    "## Quality Loop (required for non-question workflows)",
    "1. Draft or analyze output.",
    "2. Run compliance check and enumerate failed checks.",
    "3. Run one self-critique pass to catch hallucinations/coverage gaps.",
    "4. If still low-confidence, ask focused clarifying questions before finalizing.",
    "",
    "---",
    "",
  ].join("\n");
}

const SECTION_HEADER_RE = /^#{1,6}\s+/;
const BULLET_PREFIX_RE = /^[-*•]\s+/;
const NUMBERED_PREFIX_RE = /^\d+\.\s+/;
const NONE_LIKE_RE = /^(none|none identified|n\/a|na|not applicable|not needed|no blocking fields?)$/i;
type LegalReadiness = "ready" | "needs_input" | "unknown";

const escapeRegex = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const isKnowledgePlanShape = (value: unknown): value is KnowledgeRoutingPlan => {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  const lookupDynamic = obj.lookup_dynamic;
  const evergreenCalls = obj.system_evergreen_calls;
  const planHash = obj.plan_hash;
  if (!lookupDynamic || typeof lookupDynamic !== "object") return false;
  const primaryPackIds = (lookupDynamic as Record<string, unknown>).primary_pack_ids;
  return (
    Array.isArray(primaryPackIds)
    && Array.isArray(evergreenCalls)
    && typeof planHash === "string"
    && planHash.trim().length > 0
  );
};

const parseKnowledgeRoutingPlanResponse = (
  response: Record<string, unknown>,
): KnowledgeRoutingPlan | null => {
  const parseCandidate = (value: unknown): KnowledgeRoutingPlan | null => {
    if (isKnowledgePlanShape(value)) return value;
    if (typeof value !== "string" || !value.trim()) return null;
    try {
      const parsed = JSON.parse(value);
      if (isKnowledgePlanShape(parsed)) return parsed;
    } catch {}
    try {
      const parsed = decodeToon(value, { strict: false });
      if (isKnowledgePlanShape(parsed)) return parsed;
    } catch {
      return null;
    }
    return null;
  };
  return parseCandidate(response.result) ?? parseCandidate(response);
};

const fetchKnowledgeRoutingPlan = async (params: {
  threadKey: string;
  requestId: string;
  workflow: LegalWorkflow;
  dealProfile: Record<string, unknown>;
}): Promise<KnowledgeRoutingPlan | null> => {
  try {
    const response = await apiPost(
      "/tools/legal-playbook/get_knowledge_plan",
      {
        workflow: params.workflow,
        phase: "retrieval",
        deal_profile: params.dealProfile,
        max_dynamic_packs: 2,
        max_dynamic_chars: 5000,
      },
      { timeoutMs: 3_500, maxAttempts: 1 },
    );
    const plan = parseKnowledgeRoutingPlanResponse(response);
    if (!plan) {
      console.warn("legal_knowledge_plan_parse_failed", {
        thread: params.threadKey,
        requestId: params.requestId,
        workflow: params.workflow,
      });
    }
    return plan;
  } catch (error) {
    console.warn("legal_knowledge_plan_fallback", {
      thread: params.threadKey,
      requestId: params.requestId,
      workflow: params.workflow,
      error: error instanceof Error ? error.message : String(error),
    });
    return null;
  }
};

const normalizeSectionLabel = (line: string): string =>
  line
    .replace(/^#{1,6}\s*/, "")
    .replace(/[`*_]/g, "")
    .replace(/:\s*$/, "")
    .trim()
    .toLowerCase();

const isSectionBoundary = (line: string): boolean =>
  SECTION_HEADER_RE.test(line) || /^[`*_]*[A-Za-z][A-Za-z0-9 /()_-]{2,60}[`*_]*:\s*$/.test(line.trim());

const extractSectionLines = (text: string, sectionLabel: string): string[] => {
  const lines = text.split(/\r?\n/);
  const target = sectionLabel.trim().toLowerCase();
  let inSection = false;
  const out: string[] = [];
  const inlineRe = new RegExp(
    `^\\s*(?:#{1,6}\\s*)?[\\\`*_]*${escapeRegex(sectionLabel)}[\\\`*_]*\\s*:\\s*(.+)\\s*$`,
    "i",
  );
  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    if (!inSection) {
      const inlineMatch = rawLine.match(inlineRe);
      if (inlineMatch) {
        const inlineValue = inlineMatch[1]?.trim();
        if (inlineValue) out.push(inlineValue);
        inSection = true;
        continue;
      }
      const normalized = normalizeSectionLabel(rawLine);
      if (normalized === target) {
        inSection = true;
      }
      continue;
    }
    if (!trimmed) continue;
    if (isSectionBoundary(rawLine) && !BULLET_PREFIX_RE.test(trimmed) && !NUMBERED_PREFIX_RE.test(trimmed)) {
      break;
    }
    out.push(rawLine);
  }
  return out;
};

const parseSectionItems = (lines: string[]): string[] => {
  const items: string[] = [];
  let pending = "";
  const flush = () => {
    const normalized = pending.replace(/\s+/g, " ").trim();
    if (normalized) items.push(normalized);
    pending = "";
  };
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;
    if (BULLET_PREFIX_RE.test(line) || NUMBERED_PREFIX_RE.test(line)) {
      flush();
      pending = line.replace(BULLET_PREFIX_RE, "").replace(NUMBERED_PREFIX_RE, "").trim();
      continue;
    }
    if (pending) {
      pending = `${pending} ${line}`;
      continue;
    }
    items.push(line);
  }
  flush();
  return uniqueBullets(items.map((item) => item.replace(/\.$/, "").trim()).filter(Boolean));
};

const parseReadiness = (intakeText: string): LegalReadiness => {
  const match = intakeText.match(
    /^\s*(?:#{1,6}\s*)?[`*_]*Readiness[`*_]*\s*:?[\s-]*(READY|NEEDS[_\s-]?INPUT|UNKNOWN)\b/im,
  );
  if (!match) return "unknown";
  const normalized = match[1].toLowerCase().replace(/[_-]/g, " ").trim();
  if (normalized.startsWith("ready")) return "ready";
  if (normalized.startsWith("needs input")) return "needs_input";
  return "unknown";
};

const extractBlockingFieldsFromIntake = (intakeText: string): string[] =>
  parseSectionItems(extractSectionLines(intakeText, "Blocking Missing Fields")).filter(
    (item) => !NONE_LIKE_RE.test(item.toLowerCase()),
  );

const extractFollowUpsFromIntake = (intakeText: string): string[] =>
  parseSectionItems(extractSectionLines(intakeText, "DRI Follow-Ups")).filter(
    (item) => !NONE_LIKE_RE.test(item.toLowerCase()),
  );

const shouldPauseForClarification = (
  workflow: LegalWorkflow,
  intakeText: string,
  blockingFields: string[],
): boolean => {
  if (workflow === "question") return false;
  const readiness = parseReadiness(intakeText);
  if (readiness === "ready") return false;
  if (readiness === "needs_input") return true;
  return blockingFields.length > 0;
};

const clipForPrompt = (value: string, maxChars = 4500): string =>
  value.length > maxChars ? value.slice(0, maxChars) + "\n...[truncated]..." : value;

const phaseBundle = (
  outputs: Partial<Record<LegalPhase, string>>,
  phases: LegalPhase[],
  maxChars = 4500,
): string => {
  const chunks = phases
    .map((phase) => {
      const content = outputs[phase];
      if (!content) return "";
      return `## ${phase.toUpperCase()}\n${clipForPrompt(content, maxChars)}`;
    })
    .filter(Boolean);
  return chunks.join("\n\n");
};

const criticApproved = (criticText: string): boolean => {
  if (/\bCHANGES_REQUIRED\b/i.test(criticText)) return false;
  const firstNonEmpty = criticText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line.length > 0);
  return (firstNonEmpty || "").toUpperCase() === "APPROVED";
};

const TOOL_EVIDENCE_RE =
  /\b(call\s+search|call\s+legal-playbook|call\s+termsheet|get_red_lines|get_paradigm_checks|explain_clause_plan|tool evidence|source:)\b/i;

const hasToolEvidence = (value: string): boolean => TOOL_EVIDENCE_RE.test(value);
const LEGAL_MAX_FINAL_RESPONSE_CHARS = 4200;
const LEGAL_TARGET_FIRST_REPLY_CHARS = 2800;
const LEGAL_MAX_BULLET_CHARS = 220;

const normalizeBulletText = (line: string): string =>
  line
    .replace(/^[-*•]\s+/, "")
    .replace(/^\d+\.\s+/, "")
    .replace(/\s+/g, " ")
    .trim();

const trimBullet = (value: string): string => {
  const cleaned = value.trim();
  if (cleaned.length <= LEGAL_MAX_BULLET_CHARS) return cleaned;
  const cutoff = cleaned.lastIndexOf(" ", LEGAL_MAX_BULLET_CHARS);
  const idx = cutoff >= Math.floor(LEGAL_MAX_BULLET_CHARS * 0.6) ? cutoff : LEGAL_MAX_BULLET_CHARS;
  return cleaned.slice(0, idx).trimEnd() + "...";
};

const uniqueBullets = (items: string[]): string[] => {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const normalized = item.toLowerCase();
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    out.push(item);
  }
  return out;
};

const collectBulletCandidates = (value: string): string[] => {
  const bullets = value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => /^[-*•]\s+/.test(line) || /^\d+\.\s+/.test(line))
    .map(normalizeBulletText)
    .filter(Boolean)
    .map(trimBullet);
  return uniqueBullets(bullets);
};

const pickBullets = (
  pool: string[],
  matcher: RegExp,
  limit: number,
  used: Set<string>,
): string[] => {
  const selected: string[] = [];
  for (const candidate of pool) {
    if (selected.length >= limit) break;
    if (!matcher.test(candidate)) continue;
    const key = candidate.toLowerCase();
    if (used.has(key)) continue;
    used.add(key);
    selected.push(candidate);
  }
  return selected;
};

const fillBullets = (
  pool: string[],
  limit: number,
  selected: string[],
  used: Set<string>,
): void => {
  for (const candidate of pool) {
    if (selected.length >= limit) break;
    const key = candidate.toLowerCase();
    if (used.has(key)) continue;
    used.add(key);
    selected.push(candidate);
  }
};

const buildConversationFirstReply = (value: string): string => {
  const bullets = collectBulletCandidates(value);
  const used = new Set<string>();

  const red = pickBullets(
    bullets,
    /\bred[_\s-]?line\b|full ratchet|liquidation|major investor|section 220|written consent|sanctions|outbound investment|token issuance|net exercise|lockup/i,
    4,
    used,
  );
  const standard = pickBullets(
    bullets,
    /\bstandard\b|board|protective provisions|threshold|governance|defined term|consistency|approval/i,
    4,
    used,
  );
  const nice = pickBullets(
    bullets,
    /\bnice[_\s-]?to[_\s-]?have\b|carveout|rofr|style|cleanup|drafting|wording/i,
    3,
    used,
  );

  fillBullets(bullets, 4, red, used);
  fillBullets(bullets, 4, standard, used);
  fillBullets(bullets, 3, nice, used);

  const askCandidates = value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.endsWith("?"))
    .map((line) => line.replace(/^[-*•]\s+/, ""))
    .map(trimBullet);
  const asks = uniqueBullets(askCandidates).slice(0, 2);

  const response = [
    "## Draft Review (Round 1)",
    "",
    "### RED_LINE",
    ...red.map((item) => `- ${item}`),
    "",
    "### STANDARD",
    ...standard.map((item) => `- ${item}`),
    "",
    "### NICE_TO_HAVE",
    ...nice.map((item) => `- ${item}`),
    "",
    "### Next Step",
    "- If you want, I can send a clause-by-clause matrix and fallback language in the next message.",
    ...(asks.length > 0
      ? asks.map((item) => `- ${item}`)
      : [
          "- Which should I prioritize next: economics redlines, governance controls, or token package terms?",
        ]),
    "",
    "_I am not a lawyer and this is not legal advice._",
  ].join("\n");

  if (response.length <= LEGAL_MAX_FINAL_RESPONSE_CHARS) {
    return response;
  }
  return response.slice(0, LEGAL_MAX_FINAL_RESPONSE_CHARS - 36).trimEnd()
    + "\n\n_Reply `continue` for full appendix._";
};

export async function runLegalPromptLoop(params: {
  threadKey: string;
  requestId: string;
  harness: Harness;
  workflow: LegalWorkflow;
  originalRequest: string;
  files: FileAttachment[];
  userId?: string;
  model?: string | null;
  engine?: Engine | null;
  sessionEnvelope?: string;
  kickoff?: boolean;
  onPhaseStatus?: (phase: string) => Promise<void> | void;
}): Promise<string> {
  const {
    threadKey,
    requestId,
    harness,
    workflow,
    originalRequest,
    userId,
    model,
    engine,
    sessionEnvelope,
    kickoff,
  } = params;
  const outputs: Partial<Record<LegalPhase, string>> = {};
  let pendingFiles: FileAttachment[] | undefined = params.files.length > 0 ? params.files : undefined;
  const termSheetLikely = TERM_SHEET_HINT_RE.test(originalRequest);
  const dealProfile = inferLegalDealProfile(originalRequest, workflow, params.files);
  const inferredDocType = (() => {
    const candidate = dealProfile.document_type;
    return typeof candidate === "string" && candidate ? candidate : "unknown";
  })();

  const phaseExecutionBudget = (
    policy: "default" | "retrieval" | "no_tools",
  ): string[] => {
    if (policy === "no_tools") {
      return [
        "- Do not run any tool calls in this phase.",
        "- Use only prior phase outputs and the request content.",
      ];
    }
    if (policy === "retrieval") {
      return [
        "- Maximum 6 tool calls in this phase.",
        "- Run at least three distinct `search` calls in this phase.",
        "- Do not repeat identical tool calls with equivalent arguments.",
      ];
    }
    return [
      "- Maximum 2 tool calls in this phase.",
      "- Do not repeat identical tool calls with equivalent arguments.",
    ];
  };

  const runPhase = async (
    phaseLabel: string,
    promptBody: string,
    phaseStore: LegalPhase,
    policy: "default" | "retrieval" | "no_tools" = "default",
  ) => {
    await params.onPhaseStatus?.(phaseStore);
    const boundedPrompt = [
      "Style contract for this phase:",
      "- Write like a senior transactional lawyer: precise, concise, neutral-professional.",
      "- Lead with findings and action items; avoid hype, verbosity, or generic AI phrasing.",
      "- Use explicit assumptions and legal-risk qualifiers when evidence is incomplete.",
      "",
      "Execution budget for this phase:",
      ...phaseExecutionBudget(policy),
      "- If required inputs are missing, list them once and stop.",
      "",
      promptBody,
    ].join("\n");
    const result = await executeWithBusyRetries({
      threadKey,
      message: `[${phaseLabel}] ${boundedPrompt}`,
      harness,
      requestId: `${requestId}:${phaseLabel}`,
      files: pendingFiles,
      userId,
      model,
      engine,
      continueSession: true,
      legalLoopEnabled: true,
    });
    pendingFiles = undefined;
    outputs[phaseStore] = result;
    return result;
  };

  if (kickoff) {
    return runPhase(
      "finalize-kickoff",
      [
        "You are executing LEGAL PHASE: FINALIZE (KICKOFF).",
        "Respond with a concise kickoff message in lawyer-facing style.",
        "Requirements:",
        "- include this exact phrase: `I am not a lawyer; I am a legal agent created by Paradigm.`",
        "- explain capabilities: legal questions, review, drafting/revision, term sheet support",
        "- provide exactly 4 short example prompts",
        "- ask one focused follow-up question to begin work",
        "- do not run any tool calls in this phase",
        "- keep output <= 220 words and avoid marketing tone",
        "",
        "Session envelope:",
        clipForPrompt(sessionEnvelope || "", 9000),
      ].join("\n"),
      "finalize",
      "no_tools",
    );
  }

  await runPhase(
    "intake",
    [
      "You are executing LEGAL PHASE: INTAKE.",
      "Classify workflow, extract known terms, list assumptions, and list only blocking missing fields.",
      "Return sections: `Readiness` (READY or NEEDS_INPUT), `Workflow`, `Known Terms`, `Assumptions`, `Blocking Missing Fields`, `DRI Follow-Ups`.",
      "`Readiness` must be exactly `READY` or `NEEDS_INPUT`.",
      "Deterministic rule:",
      "- If `Blocking Missing Fields` has any concrete item, set `Readiness: NEEDS_INPUT`.",
      "- If no blocking items, set `Readiness: READY` and write `none` under `Blocking Missing Fields`.",
      "- Do not ask user questions in INTAKE.",
      sessionEnvelope
        ? [
            "",
            "Session envelope (thread + context):",
            clipForPrompt(sessionEnvelope, 9000),
          ].join("\n")
        : "",
      "",
      "Original request:",
      clipForPrompt(originalRequest),
    ].join("\n"),
    "intake",
    "no_tools",
  );

  const intakeOutput = outputs.intake || "";
  const blockingFields = extractBlockingFieldsFromIntake(intakeOutput);
  const followUps = extractFollowUpsFromIntake(intakeOutput);
  if (shouldPauseForClarification(workflow, intakeOutput, blockingFields)) {
    const questionPool = uniqueBullets([
      ...followUps,
      ...blockingFields.map((item) => `Please provide: ${item}`),
    ]).slice(0, 4);
    return runPhase(
      "clarify",
      [
        "You are executing LEGAL PHASE: CLARIFY.",
        "Do not produce the final legal analysis/draft yet.",
        "Ask only for the minimum inputs needed to proceed with high confidence.",
        "Return sections: `What I Need From You`, `Reply Template`, `What Happens Next`.",
        "Requirements:",
        "- ask at most 4 concise, high-signal questions",
        "- if a source document is required, explicitly ask the user to attach or paste it in this Slack thread",
        "- provide one optional defaults path so the user can reply quickly",
        "- do not run any tool calls in this phase",
        "- keep total output under 180 words",
        "- include one-line legal boundary reminder",
        "",
        `Workflow: ${workflow}`,
        "",
        "Original request:",
        clipForPrompt(originalRequest),
        "",
        "Blocking missing fields from intake:",
        ...(blockingFields.length > 0 ? blockingFields.map((item) => `- ${item}`) : ["- Not explicitly listed"]),
        "",
        "Suggested follow-ups from intake:",
        ...(questionPool.length > 0 ? questionPool.map((item) => `- ${item}`) : ["- Ask for the minimum required deal terms and source document."]),
      ].join("\n"),
      "clarify",
      "no_tools",
    );
  }

  const knowledgeRoutingPlan =
    workflow === "question"
      ? null
      : await fetchKnowledgeRoutingPlan({
          threadKey,
          requestId,
          workflow,
          dealProfile,
        });

  await runPhase(
    "retrieval",
    [
      "You are executing LEGAL PHASE: RETRIEVAL.",
      "Two tasks: (A) deterministic knowledge planning, (B) shared-search evidence retrieval.",
      "",
      knowledgeRoutingPlan
        ? "A) Controller-provided routing plan (use this first):"
        : "A) Knowledge planning and loading:",
      knowledgeRoutingPlan
        ? "Use the precomputed routing plan below. Execute `system_evergreen_calls` first, then load `lookup_dynamic.primary_pack_ids`."
        : '- Build plan first: `call legal-playbook get_knowledge_plan \'{"workflow":"<workflow>","phase":"retrieval","deal_profile":{"company_type":"<ai|other>","token_relevant":<true|false>},"max_dynamic_packs":2,"max_dynamic_chars":5000}\'`',
      knowledgeRoutingPlan
        ? "If the plan is malformed or missing, regenerate via `get_knowledge_plan` once."
        : "- Execute all `system_evergreen_calls` from the returned plan.",
      "- Load only `lookup_dynamic.primary_pack_ids` via `get_knowledge_pack`.",
      "- If evidence is still insufficient, load at most one contingency pack.",
      "- Hard conflict rule: policy rules are controlling; canonical internal financing context overrides precedent outliers and generalized market guidance.",
      "",
      workflow === "question"
        ? "B) Shared search — run at most two focused searches only if needed to verify material claims."
        : "B) Shared search — run at least three focused searches using `call search \"<query>\" 8`:",
      workflow === "question" ? "- one clause/legal-standard verification query" : "- one company/deal specific query",
      workflow === "question"
        ? "- one precedent/authority verification query when confidence is otherwise low"
        : "- one clause/legal-standard query (NVCA + playbook-relevant terms)",
      workflow === "question"
        ? ""
        : "- one precedent/style query aligned to drafting tone and negotiation posture",
      "",
      "Return sections: `Knowledge Plan`, `Knowledge Loaded`, `Search Queries`, `Evidence Table`, `Evidence Gaps`.",
      "In `Evidence Table`, number rows as `E1`, `E2`, ... and include: source tier (policy/canonical/precedent/general), source, why it matters, and direct quoted snippet.",
      "If conflicting sources appear, add `Conflict Resolution` with higher-priority source and rationale.",
      "",
      "Original request:",
      clipForPrompt(originalRequest),
      knowledgeRoutingPlan
        ? [
            "",
            "Precomputed routing plan:",
            clipForPrompt(JSON.stringify(knowledgeRoutingPlan, null, 2), 8000),
          ].join("\n")
        : "",
      "",
      "Intake output:",
      phaseBundle(outputs, ["intake"]),
    ].join("\n"),
    "retrieval",
    "retrieval",
  );

  if (workflow === "question") {
    const questionResponse = await runPhase(
      "finalize",
      [
        "You are executing LEGAL PHASE: FINALIZE (QUESTION workflow).",
        "Produce the final user-facing answer.",
        "Requirements:",
        "- concise direct answer",
        "- explicit assumptions + uncertainty boundaries",
        "- optional next actions",
        "- one-line reminder: legal assistant, not a lawyer",
        "- do not run additional tool calls in this phase",
        "",
        "Prior phase outputs:",
        phaseBundle(outputs, ["intake", "retrieval"]),
      ].join("\n"),
      "finalize",
      "no_tools",
    );
    return questionResponse.length > LEGAL_MAX_FINAL_RESPONSE_CHARS
      ? buildConversationFirstReply(questionResponse)
      : questionResponse;
  }

  await runPhase(
    "authority",
    [
      "You are executing LEGAL PHASE: AUTHORITY.",
      "Use playbook and known context to determine legal baseline and applicable standards.",
      "Explicitly identify: red-line applicability, stage/ownership leverage, doc-type assumptions, and evidence quality.",
      "Return sections: `Applicable Standards`, `Red-Line Scope`, `Leverage Calibration`, `Evidence Gaps`.",
      "",
      "Prior phase outputs:",
      phaseBundle(outputs, ["intake", "retrieval"]),
    ].join("\n"),
    "authority",
  );

  await runPhase(
    "analysis",
    [
      "You are executing LEGAL PHASE: ANALYSIS.",
      "Analyze the request against standards and prepare concrete drafting/review direction.",
      "Return sections: `Core Analysis`, `Risks`, `Action Plan`, `Negotiation Posture`, `NVCA Baseline Checks`.",
      "- Keep analysis concise and scannable; avoid repeating prior phase text.",
      "- For NVCA checks, prefer compact tables/bullets over long prose.",
      "- If tool retrieval fails, include one brief limitation note and still deliver full requested analysis.",
      termSheetLikely
        ? "- Include a term-sheet field map with explicit values/defaults for: company_name, investment_amount, instrument_type, valuation, series, stage, intent, is_lead_investor, option_pool_percent, board_rights, debt_threshold, legal_fee_cap, no_shop_days, token_rights."
        : "",
      termSheetLikely
        ? '- Pull at least one precedent signal from platform retrieval (`call search "<company/stage/instrument + key clause focus>" 8`) and cite it in analysis.'
        : "",
      "",
      "Prior phase outputs:",
      phaseBundle(outputs, ["intake", "retrieval", "authority"]),
    ].join("\n"),
    "analysis",
  );

  let currentDraft = await runPhase(
    "draft-1",
    [
      "You are executing LEGAL PHASE: DRAFT.",
      "Produce a full candidate output for internal review.",
      "Requirements:",
      "- do not claim tools/subagents were used unless this turn contains those outputs",
      "- include all nits; do not self-filter low-severity findings",
      "- include explicit `RED_LINE`, `STANDARD`, and `NICE_TO_HAVE` sections",
      "- use `RED_LINE` only for explicit red-line violations; otherwise prefer `STANDARD` when evidence is incomplete",
      "- when recommending concessions, explain speed/relationship rationale and stage/ownership leverage",
      "- route economics changes to investment-team decision points",
      "- preserve user-specified terms unless conflicting with explicit red lines",
      "- include assumptions where necessary",
      "- keep output compact (target <= 1200 words unless user explicitly requests long-form)",
      "- never return only provenance/limitation notes; always return the requested draft/review substance",
      termSheetLikely
        ? "- For term-sheet drafting/revision, use `call termsheet create_term_sheet '<json>'`, then `call termsheet explain_clause_plan '<json>'`, then `call termsheet generate_document_package '<json>'` to produce clean/redline artifacts; if a tool call fails, state that limitation once and continue with best-effort structured draft."
        : "",
      "",
      "Prior phase outputs:",
      phaseBundle(outputs, ["intake", "retrieval", "authority", "analysis"]),
    ].join("\n"),
    "draft",
  );

  for (let i = 1; i <= LEGAL_MAX_REVIEW_LOOPS; i += 1) {
    const critic = await runPhase(
      `critic-${i}`,
      [
        "You are executing LEGAL PHASE: CRITIC.",
        "Review the draft against the full legal quality bar.",
        "First non-empty line must be exactly `APPROVED` or `CHANGES_REQUIRED`.",
        "Then include sections: `Issues`, `Missing Coverage`, `Recommended Fixes`, `NVCA Coverage Gaps`.",
        "",
        "Candidate draft:",
        clipForPrompt(currentDraft, 9000),
      ].join("\n"),
      "critic",
    );

    if (criticApproved(critic)) {
      break;
    }

    currentDraft = await runPhase(
      `revise-${i}`,
      [
        "You are executing LEGAL PHASE: REVISE.",
        "Revise the draft using the critic feedback while preserving valid user constraints.",
        "Return a complete revised draft candidate.",
        "",
        "Previous draft:",
        clipForPrompt(currentDraft, 9000),
        "",
        "Critic feedback:",
        clipForPrompt(critic, 9000),
      ].join("\n"),
      "revise",
    );
  }

  let compliance = await runPhase(
    "compliance",
    [
      "You are executing LEGAL PHASE: COMPLIANCE.",
      "Evaluate draft against 16 red lines and 11 Paradigm checks.",
      `Run \`call legal-playbook check_compliance '{"document_text":"...", "document_type":"${inferredDocType}"}'\` using the draft content.`,
      "Then run `call legal-playbook score_quality '{\"total_claims\":N,\"verified_claims\":N,\"errors\":N,\"gaps\":N}'` and include that score in Confidence.",
      "Compute confidence score: (verified/max(total,1))*100 - (2*errors) - (1*gaps).",
      "Return sections: `Red Line Status`, `Paradigm Check Matrix`, `Leverage Calibration`, `NVCA Baseline Checks`, `Confidence`.",
      "",
      "Draft to evaluate:",
      clipForPrompt(currentDraft, 9000),
    ].join("\n"),
    "compliance",
  );

  const groundingCorpus = phaseBundle(
    outputs,
    ["retrieval", "authority", "analysis", "draft", "compliance"],
    7000,
  );
  if (!hasToolEvidence(groundingCorpus)) {
    currentDraft = await runPhase(
      "draft-grounding",
      [
        "You are executing LEGAL PHASE: DRAFT (GROUNDING REMEDIATION).",
        "Grounding remediation is required because prior phases did not include explicit tool evidence.",
        "Before drafting, run platform retrieval and legal-playbook checks and use those outputs directly.",
        'Run `call search "<company/stage/instrument + clause focus>" 8` with a narrow query and cite concrete snippets.',
        "Return sections: `Tool Evidence`, `Updated Draft`.",
        "Tool Evidence must list exact tool/method names used and the key retrieved facts.",
        "",
        "Prior phase outputs:",
        phaseBundle(outputs, ["intake", "retrieval", "authority", "analysis", "draft"]),
      ].join("\n"),
      "draft",
    );

    compliance = await runPhase(
      "compliance-grounding",
      [
        "You are executing LEGAL PHASE: COMPLIANCE (GROUNDING REMEDIATION).",
        "Re-evaluate the updated draft and include explicit tool-grounding evidence.",
        `Use document_type \`${inferredDocType}\` for any compliance tool calls in this phase.`,
        "Return sections: `Tool Evidence`, `Red Line Status`, `Paradigm Check Matrix`, `Leverage Calibration`, `NVCA Baseline Checks`, `Confidence`.",
        "",
        "Draft to evaluate:",
        clipForPrompt(currentDraft, 9000),
      ].join("\n"),
      "compliance",
    );
  }

  let finalResponse = await runPhase(
    "finalize",
    [
      "You are executing LEGAL PHASE: FINALIZE.",
      "Produce the final user-facing response.",
      "Requirements:",
      "- do not invent tool/provenance claims; only report retrieval outcomes shown in phase outputs",
      "- structured, concise, decision-useful",
      "- include all nits in findings, but keep each item brief",
      "- include severity-ranked findings",
      "- include economics escalation notes where terms changed from likely deal intent",
      "- include explicit negotiation posture (speed, relationship, leverage)",
      "- include a `Tool Evidence` section summarizing concrete legal-playbook/termsheet retrieval used in this turn",
      "- include `NVCA Baseline Checks` section",
      "- include confidence score + unresolved uncertainty",
      "- cite each substantive finding to one or more evidence rows from `Evidence Table` (for example `[E2]`); if uncited, mark `[ASSUMPTION]`",
      "- strictly honor any explicit user length cap in the request",
      "- communicate like a senior transactional lawyer: crisp, practical, and commercially grounded",
      "- default to back-and-forth cadence: this should be a first-pass brief, not a full appendix dump",
      "- keep output compact (target <= 450 words; prioritize bullets/table over paragraphs)",
      "- include at most: 4 RED_LINE, 4 STANDARD, 3 NICE_TO_HAVE items in this first response",
      "- ask follow-up questions only if unresolved blocking inputs remain; otherwise end with one concrete next action",
      "- hard limit for this response: 3200 characters",
      "- if tools are unavailable, add one-line limitation and still provide complete requested analysis",
      "- include one-line reminder containing: `not a lawyer` or `not legal advice`",
      "",
      "Phase outputs:",
      phaseBundle(outputs, ["intake", "retrieval", "authority", "analysis"]),
      "",
      "Final draft candidate:",
      clipForPrompt(currentDraft, 9000),
      "",
      "Compliance results:",
      clipForPrompt(compliance, 9000),
    ].join("\n"),
    "finalize",
  );
  if (finalResponse.length > LEGAL_TARGET_FIRST_REPLY_CHARS) {
    finalResponse = buildConversationFirstReply(finalResponse);
  }
  if (finalResponse.length > LEGAL_MAX_FINAL_RESPONSE_CHARS) {
    finalResponse = buildConversationFirstReply(finalResponse);
  }
  return finalResponse;
}

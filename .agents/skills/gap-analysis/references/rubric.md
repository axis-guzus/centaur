# Rubric

Use a 0-4 integer score for each dimension.

For each dimension, answer the binary sub-questions first, then use the count of "yes" answers as a guide for the score. Write a one-sentence reasoning trace before assigning the score.

## Completion
JSON key: `completion`

Binary sub-questions:

- Did the bot attempt the requested task? (yes/no)
- Did it finish the core deliverable? (yes/no)
- Did it address all parts of the request, not just the first? (yes/no)
- Would the user need to re-ask or do significant follow-up work? (yes/no — "no" means complete)

Score anchors:

- 0: Did not attempt or completely wrong task.
- 1: Attempted but clearly unfinished or addressed only a fragment.
- 2: Completed a narrow or partial version; user must do meaningful follow-up.
- 3: Completed the task with small gaps or minor missing pieces.
- 4: Fully completed the task as requested.

## Correctness
JSON key: `correctness`

Binary sub-questions:

- Is the core answer or deliverable factually/technically correct? (yes/no)
- Are there any material errors that would mislead the user? (yes/no — "no" is good)
- Would an expert in the domain agree with the result? (yes/no)
- Is the answer internally consistent? (yes/no)

Score anchors:

- 0: Materially wrong or fabricated.
- 1: Mostly wrong or misleading on the core question.
- 2: Mixed accuracy with meaningful flaws.
- 3: Mostly correct with minor issues.
- 4: Materially correct; an expert would agree.

## Research Quality
JSON key: `research_quality`

Binary sub-questions:

- Did the bot read the relevant code, docs, or data before answering? (yes/no)
- Did it gather evidence proportional to the complexity of the task? (yes/no)
- Did it miss obviously relevant sources that were available? (yes/no — "no" is good)
- Did it use search, file reads, or tool calls to verify its assumptions? (yes/no)

Score anchors:

- 0: No meaningful evidence gathering.
- 1: Thin or misdirected research; key sources missed.
- 2: Some relevant context but important gaps.
- 3: Good research with minor omissions.
- 4: Strong, well-targeted evidence gathering.

## Verification Quality
JSON key: `verification_quality`

First decide: **does this task type require verification?**

Verification is required when the bot produced code changes, config changes, factual claims that could be checked, data transformations, or any deliverable where correctness can be tested.

Verification is **not required** for conversational brainstorming, opinion questions, open-ended ideation, or simple acknowledgment tasks. If verification is not required, score 4 and note "verification not applicable for this task type" in the reasoning trace.

Critical override: if the execution failed, was cancelled, timed out, or never
delivered a usable result, verification is **not** "not applicable" — it is a
failure of the task. In that case, `verification_quality` must be `0` unless
the evidence pack shows a concrete verification step happened before the task
failed.

Binary sub-questions (when verification is required):

- Did the bot validate its answer or change before delivering? (yes/no)
- Did it run tests, lint, or manual checks where appropriate? (yes/no)
- Did it confirm the deliverable works end-to-end, not just locally? (yes/no)
- If it made code changes, did it verify the code compiles and passes checks? (yes/no)

Score anchors:

- 0: No verification where verification was clearly needed.
- 1: Very weak or performative verification.
- 2: Partial verification with meaningful gaps.
- 3: Good verification with minor omissions.
- 4: Strong verification appropriate to the task, or verification not applicable for this task type.

## Tool-Calling Quality
JSON key: `tool_calling_quality`

Binary sub-questions:

- Did the bot choose the right tools for the task? (yes/no)
- Did it avoid unnecessary or redundant tool calls? (yes/no)
- Did it recover well from tool errors? (yes/no)
- Did it use available tools that would have materially improved the result? (yes/no)

Score anchors:

- 0: Misused tools or relied on clearly wrong tools.
- 1: Significant tool inefficiency or poor error recovery.
- 2: Mixed tool choices with avoidable issues.
- 3: Good tool choices with minor waste or friction.
- 4: Strong tool choices and recovery behavior.

## Subagent-Usage Quality
JSON key: `subagent_usage_quality`

Binary sub-questions:

- Did the task warrant subagent delegation? (yes/no)
- If yes, did the bot use subagents? (yes/no)
- Were subagents scoped well (not too broad, not too narrow)? (yes/no)
- Were subagent results integrated properly into the final answer? (yes/no)

Critical override: if the execution failed or never delivered a usable result,
do not award a default `4` just because subagent usage was not obviously
required. A task that died before delivery should score `0` unless there is
clear positive evidence that subagent use materially improved the run before it
failed.

Score anchors:

- 0: Clear misuse of subagents or total absence when strongly needed.
- 1: Significant underuse or poor scoping.
- 2: Mixed quality in subagent use.
- 3: Good subagent judgment with minor issues.
- 4: Strong subagent judgment and integration.

## Communication Quality
JSON key: `communication_quality`

Binary sub-questions:

- Did the bot answer in a way the user could understand and act on? (yes/no)
- Did it lead with the answer rather than preamble? (yes/no)
- Did it flag uncertainty, caveats, or risks where appropriate? (yes/no)
- Would the user know what to do next after reading the response? (yes/no)

Score anchors:

- 0: Confusing, unhelpful, or misleading communication.
- 1: Hard to parse or buried answer; user must dig.
- 2: Understandable but could be clearer or more direct.
- 3: Clear and actionable with minor presentation issues.
- 4: Excellent communication; the user knows exactly what happened and what to do next.

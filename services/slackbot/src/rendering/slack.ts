import type { WebClient } from '@slack/web-api'
import {
  ChatSDKRenderer,
  chatSDKOperationSchema,
  parseRendererDoneEvent,
  parseRendererEvent,
  rendererContentToMarkdown,
  rendererOpenInputSchema,
  rendererTargetSchema,
  type ParsedRendererMessageSnapshotEvent,
  type RendererDoneEvent,
  type RendererEvent,
  type RendererInterface,
  type RendererOpenInput,
  type RendererOpenResult,
  type RendererRenderResult
} from '@centaur/rendering'
import { z } from 'zod'
import { AgentSessionRenderer } from '../slack/agent-session'

export const slackRendererTargetSchema = z
  .object({
    channel: z.string().min(1),
    parentTs: z.string().min(1),
    recipientTeamId: z.string().min(1),
    recipientUserId: z.string().min(1)
  })
  .strict()

export const slackRendererTargetEnvelopeSchema = rendererTargetSchema
  .extend({
    platform: z.literal('slack'),
    slack: slackRendererTargetSchema
  })
  .strict()

export const slackRendererOpenInputSchema = rendererOpenInputSchema
  .extend({
    target: slackRendererTargetEnvelopeSchema
  })
  .strict()

export type SlackRendererTarget = z.output<typeof slackRendererTargetSchema>
export type SlackRendererOpenInput = z.input<typeof slackRendererOpenInputSchema>
export type ParsedSlackRendererOpenInput = z.output<typeof slackRendererOpenInputSchema>

export function parseSlackRendererOpenInput(input: unknown): ParsedSlackRendererOpenInput {
  return slackRendererOpenInputSchema.parse(input)
}

export const slackSessionOpenedOperationSchema = z
  .object({
    type: z.literal('slack.session.opened'),
    sessionId: z.string(),
    agentSessionId: z.string(),
    chat: z.array(chatSDKOperationSchema)
  })
  .strict()

export const slackStatusUpdatedOperationSchema = z
  .object({
    type: z.literal('slack.status.updated'),
    sessionId: z.string(),
    status: z.string(),
    chat: z.array(chatSDKOperationSchema)
  })
  .strict()

export const slackTextDeltaOperationSchema = z
  .object({
    type: z.literal('slack.text.delta'),
    sessionId: z.string(),
    acceptedChars: z.number().int().nonnegative(),
    chat: z.array(chatSDKOperationSchema)
  })
  .strict()

export const slackTaskUpdatedOperationSchema = z
  .object({
    type: z.literal('slack.task.updated'),
    sessionId: z.string(),
    taskId: z.string(),
    chat: z.array(chatSDKOperationSchema)
  })
  .strict()

export const slackSessionClosedOperationSchema = z
  .object({
    type: z.literal('slack.session.closed'),
    sessionId: z.string(),
    streamedTextChars: z.number().int().nonnegative(),
    chat: z.array(chatSDKOperationSchema)
  })
  .strict()

export const slackRendererOperationSchema = z.discriminatedUnion('type', [
  slackSessionOpenedOperationSchema,
  slackStatusUpdatedOperationSchema,
  slackTextDeltaOperationSchema,
  slackTaskUpdatedOperationSchema,
  slackSessionClosedOperationSchema
])

export type SlackRendererOperation = z.output<typeof slackRendererOperationSchema>

type SlackRendererSessionState = {
  agentSessionId: string
  target: SlackRendererTarget
  deliveredText: string
}

export class SlackChatSDKRenderer implements RendererInterface<
  SlackRendererOperation[],
  SlackRendererOpenInput
> {
  readonly kind = 'slack-chat-sdk'
  private readonly agentRenderer: AgentSessionRenderer
  private readonly sessions = new Map<string, SlackRendererSessionState>()

  constructor(
    private readonly client: WebClient,
    private readonly chatRenderer: ChatSDKRenderer = new ChatSDKRenderer()
  ) {
    this.agentRenderer = new AgentSessionRenderer(client)
  }

  async open(input: SlackRendererOpenInput): Promise<RendererOpenResult<SlackRendererOperation[]>> {
    const parsed = parseSlackRendererOpenInput(input)
    const target = parsed.target.slack
    const chat = await this.chatRenderer.open(chatOpenInputFor(parsed))
    const agent = await this.agentRenderer.open({
      channel: target.channel,
      parentTs: target.parentTs,
      recipientTeamId: target.recipientTeamId,
      recipientUserId: target.recipientUserId,
      title: parsed.title,
      header: parsed.header
    })

    this.sessions.set(chat.sessionId, {
      agentSessionId: agent.sessionId,
      target,
      deliveredText: ''
    })

    return {
      sessionId: chat.sessionId,
      output: [
        {
          type: 'slack.session.opened',
          sessionId: chat.sessionId,
          agentSessionId: agent.sessionId,
          chat: chat.output
        }
      ]
    }
  }

  async render(
    sessionId: string,
    event: RendererEvent
  ): Promise<RendererRenderResult<SlackRendererOperation[]>> {
    const parsed = parseRendererEvent(event)
    if (parsed.type === 'renderer.done') return this.close(sessionId, parsed)

    const state = this.requireSession(sessionId)
    const chat = await this.chatRenderer.render(sessionId, parsed)

    if (parsed.type === 'renderer.status') {
      const response = await this.client.assistant.threads.setStatus({
        channel_id: state.target.channel,
        thread_ts: state.target.parentTs,
        status: parsed.status,
        ...(parsed.status || parsed.loadingMessages?.length
          ? { loading_messages: parsed.loadingMessages ?? [parsed.status] }
          : {})
      })
      if (!response.ok) throw new Error(response.error ?? 'assistant.threads.setStatus failed')
      return {
        output: [
          {
            type: 'slack.status.updated',
            sessionId,
            status: parsed.status,
            chat: chat.output
          }
        ]
      }
    }

    if (parsed.type === 'renderer.message.delta') {
      const acceptedChars = await this.agentRenderer.textDelta(state.agentSessionId, parsed.text, {
        force: parsed.flush ?? true,
        planPrefix: true
      })
      state.deliveredText += parsed.text.slice(0, acceptedChars)
      return {
        output: [
          {
            type: 'slack.text.delta',
            sessionId,
            acceptedChars,
            chat: chat.output
          }
        ]
      }
    }

    if (parsed.type === 'renderer.message.snapshot') {
      const acceptedChars = await this.renderSnapshot(state, parsed)
      return {
        output: [
          {
            type: 'slack.text.delta',
            sessionId,
            acceptedChars,
            chat: chat.output
          }
        ]
      }
    }

    await this.agentRenderer.step(state.agentSessionId, {
      id: parsed.task.id,
      title: parsed.task.title,
      status: parsed.task.status,
      details: rendererContentToMarkdown(parsed.task.details),
      output: rendererContentToMarkdown(parsed.task.output)
    })
    return {
      output: [
        {
          type: 'slack.task.updated',
          sessionId,
          taskId: parsed.task.id,
          chat: chat.output
        }
      ]
    }
  }

  async close(
    sessionId: string,
    event: RendererDoneEvent = { type: 'renderer.done' }
  ): Promise<RendererRenderResult<SlackRendererOperation[]>> {
    const parsed = parseRendererDoneEvent(event)
    const state = this.requireSession(sessionId)
    const chat = await this.chatRenderer.close(sessionId, parsed)
    const done = await this.agentRenderer.done(state.agentSessionId, {
      streamFinalUpdates: true,
      answerMarkdown: parsed.finalText
    })
    this.sessions.delete(sessionId)
    return {
      output: [
        {
          type: 'slack.session.closed',
          sessionId,
          streamedTextChars: done.streamedTextChars,
          chat: chat.output
        }
      ]
    }
  }

  private async renderSnapshot(
    state: SlackRendererSessionState,
    event: ParsedRendererMessageSnapshotEvent
  ): Promise<number> {
    const delta = snapshotDelta(state.deliveredText, event.text)
    if (!delta) {
      state.deliveredText = event.text
      return 0
    }
    const acceptedChars = await this.agentRenderer.textDelta(state.agentSessionId, delta, {
      force: true,
      planPrefix: true
    })
    state.deliveredText = event.text
    return acceptedChars
  }

  private requireSession(sessionId: string): SlackRendererSessionState {
    const state = this.sessions.get(sessionId)
    if (!state) throw new Error('renderer_session_not_found')
    return state
  }
}

function chatOpenInputFor(input: ParsedSlackRendererOpenInput): RendererOpenInput {
  return {
    ...input,
    target: {
      platform: input.target.platform,
      threadKey: input.target.threadKey,
      surface: input.target.surface,
      metadata: input.target.metadata
    }
  }
}

function snapshotDelta(previous: string, next: string): string {
  if (!next) return ''
  if (!previous) return next
  if (next.startsWith(previous)) return next.slice(previous.length)
  return next
}

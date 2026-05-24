import type { AnyBlock } from '@slack/types'
import { ulid } from '@std/ulid'
import type { StreamRichText, StreamTaskStatus } from './streaming'

type StreamChunk =
  | { type: 'markdown_text'; text: string }
  | {
      type: 'task_update'
      id: string
      title: string
      status: StreamTaskStatus
      details?: string
      output?: string
    }
  | { type: 'plan_update'; title: string }

type ChatSdkStreamAdapter = {
  startTyping?(threadId: string, status?: string): Promise<void>
  stream(
    threadId: string,
    textStream: AsyncIterable<string | StreamChunk>,
    options?: {
      recipientTeamId?: string
      recipientUserId?: string
      taskDisplayMode?: 'timeline' | 'plan'
      stopBlocks?: unknown[]
    }
  ): Promise<unknown>
}

type AgentSessionState = {
  id: string
  channel: string
  parentTs: string
  recipientTeamId: string
  recipientUserId: string
  header?: string
  done: boolean
  queue: AsyncChunkQueue
  streamPromise: Promise<unknown>
  streamedMarkdown: string
  streamedTextChars: number
}

export type OpenAgentSessionInput = {
  channel: string
  parentTs: string
  recipientTeamId: string
  recipientUserId: string
  title?: string
  header?: string
}

export type StepInput = {
  id: string
  title: string
  status?: StreamTaskStatus
  details?: StreamRichText | string
  output?: StreamRichText | string
}

export type StepOptions = {
  flush?: boolean
}

export type TextOptions = {
  flush?: boolean
  force?: boolean
  planPrefix?: boolean
}

export type DoneOptions = {
  streamFinalUpdates?: boolean
  commentaryMarkdown?: string
  answerMarkdown?: string
}

const sessions = new Map<string, AgentSessionState>()
const sessionQueues = new Map<string, Promise<void>>()
const THINKING_STATUS = 'Thinking...'

let chatSdkStreamAdapter: ChatSdkStreamAdapter | undefined

export function configureAgentSessionChatSdk(adapter: ChatSdkStreamAdapter): void {
  chatSdkStreamAdapter = adapter
}

export class AgentSessionRenderer {
  async open(input: OpenAgentSessionInput): Promise<{ sessionId: string }> {
    const adapter = requireChatSdkAdapter()
    const id = ulid()
    const queue = new AsyncChunkQueue()
    const state: AgentSessionState = {
      id,
      channel: input.channel,
      parentTs: input.parentTs,
      recipientTeamId: input.recipientTeamId,
      recipientUserId: input.recipientUserId,
      header: input.header?.trim() || undefined,
      done: false,
      queue,
      streamPromise: Promise.resolve(),
      streamedMarkdown: '',
      streamedTextChars: 0
    }
    const threadId = slackThreadId(state)
    state.streamPromise = (async () => {
      await adapter.startTyping?.(threadId, THINKING_STATUS)
      if (state.header) state.queue.push(markdownChunk(headerMarkdown(state.header) + '\n\n', state))
      await adapter.stream(threadId, state.queue, {
        recipientTeamId: state.recipientTeamId,
        recipientUserId: state.recipientUserId,
        taskDisplayMode: 'plan'
      })
    })()
    sessions.set(id, state)
    return { sessionId: id }
  }

  async text(sessionId: string, markdown: string): Promise<number> {
    const state = requireSession(sessionId)
    state.queue.push(markdownChunk(markdown, state))
    return markdown.length
  }

  async textDelta(sessionId: string, markdownDelta: string, _opts: TextOptions = {}): Promise<number> {
    if (!markdownDelta) return 0
    const state = requireSession(sessionId)
    state.queue.push(markdownChunk(markdownDelta, state))
    return markdownDelta.length
  }

  streamedTextChars(sessionId: string): number {
    return requireSession(sessionId).streamedTextChars
  }

  async blocks(sessionId: string, blocks: AnyBlock[], _opts: { planPrefix?: boolean } = {}): Promise<void> {
    if (!blocks.length) return
    const state = requireSession(sessionId)
    state.queue.push(markdownChunk(blockFallbackMarkdown(blocks), state))
  }

  async step(sessionId: string, input: StepInput, _opts: StepOptions = {}): Promise<void> {
    const state = requireSession(sessionId)
    state.queue.push({
      type: 'task_update',
      id: input.id,
      title: input.title,
      status: input.status ?? 'in_progress',
      details: richTextToMarkdown(input.details),
      output: richTextToMarkdown(input.output)
    })
  }

  async done(sessionId: string, opts: DoneOptions = {}): Promise<{ streamedTextChars: number }> {
    const state = requireSession(sessionId)
    state.done = true
    const finalText = [opts.commentaryMarkdown, opts.answerMarkdown].filter(Boolean).join('\n\n')
    if (finalText.trim() && !state.streamedMarkdown.trim()) {
      state.queue.push(markdownChunk(finalText, state))
    }
    state.queue.close()
    try {
      await state.streamPromise
    } finally {
      sessions.delete(sessionId)
    }
    return { streamedTextChars: state.streamedTextChars }
  }
}

function requireChatSdkAdapter(): ChatSdkStreamAdapter {
  if (!chatSdkStreamAdapter) throw new Error('chat_sdk_slack_adapter_not_configured')
  return chatSdkStreamAdapter
}

function requireSession(sessionId: string): AgentSessionState {
  const state = sessions.get(sessionId)
  if (!state) throw new Error(`Unknown agent session: ${sessionId}`)
  if (state.done) throw new Error(`Agent session already completed: ${sessionId}`)
  return state
}

function slackThreadId(state: AgentSessionState): string {
  return `slack:${state.channel}:${state.parentTs}`
}

function headerMarkdown(header: string): string {
  return `_${header.trim()}_`
}

function markdownChunk(text: string, state: AgentSessionState): StreamChunk {
  state.streamedMarkdown += text
  state.streamedTextChars += text.length
  return { type: 'markdown_text', text }
}

class AsyncChunkQueue implements AsyncIterable<string | StreamChunk> {
  private readonly values: Array<string | StreamChunk> = []
  private readonly waiters: Array<() => void> = []
  private closed = false

  push(value: string | StreamChunk): void {
    if (this.closed) return
    this.values.push(value)
    this.waiters.shift()?.()
  }

  close(): void {
    this.closed = true
    while (this.waiters.length) this.waiters.shift()?.()
  }

  async *[Symbol.asyncIterator](): AsyncIterator<string | StreamChunk> {
    while (!this.closed || this.values.length) {
      const next = this.values.shift()
      if (next) {
        yield next
        continue
      }
      await new Promise<void>(resolve => this.waiters.push(resolve))
    }
  }
}

function richTextToMarkdown(value: StreamRichText | string | undefined): string | undefined {
  if (typeof value === 'string') return value
  if (!value) return undefined
  return richTextElementsToMarkdown(value.elements)
}

function richTextElementsToMarkdown(elements: StreamRichText['elements']): string {
  return elements
    .map(element => {
      if (element.type === 'rich_text_preformatted') {
        const body = element.elements.map(child => child.text).join('')
        const language = (element as { language?: string }).language ?? ''
        return `\`\`\`${language}\n${body}\n\`\`\``
      }
      return element.elements
        .map(child => {
          if (child.type === 'link') return child.text ? `[${child.text}](${child.url})` : child.url
          if (child.type === 'user') return `<@${child.user_id}>`
          return 'text' in child ? child.text : ''
        })
        .join('')
    })
    .join('\n')
}

function blockFallbackMarkdown(blocks: AnyBlock[]): string {
  return blocks
    .map(block => {
      const text = (block as { text?: unknown }).text
      if (typeof text === 'string') return text
      const blockText = (block as { text?: { text?: unknown } }).text?.text
      if (typeof blockText === 'string') return blockText
      return ''
    })
    .filter(Boolean)
    .join('\n\n')
}

export async function withAgentSessionLock<T>(sessionId: string, fn: () => Promise<T>): Promise<T> {
  const previous = sessionQueues.get(sessionId) ?? Promise.resolve()
  const run = previous.catch(() => undefined).then(fn)
  const cleanup = run.then(
    () => undefined,
    () => undefined
  )
  sessionQueues.set(sessionId, cleanup)
  void cleanup.finally(() => {
    if (sessionQueues.get(sessionId) === cleanup) sessionQueues.delete(sessionId)
  })
  return run
}

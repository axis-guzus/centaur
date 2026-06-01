import {
  codeBlock,
  link as chatLink,
  paragraph,
  parseMarkdown,
  root,
  strong,
  text as chatText,
  type Content,
  type PostableMessage,
  type Root,
  type StreamChunk
} from 'chat'
import { ulid } from '@std/ulid'
import { z } from 'zod'
import {
  rendererContentToMarkdown,
  rendererMetadataSchema,
  rendererTargetSchema,
  type RendererContent,
  type RendererDoneEvent,
  type RendererEvent,
  type RendererOpenInput,
  type RendererTarget,
  type RendererTask
} from './schema'
import {
  parseRendererDoneEvent,
  parseRendererEvent,
  parseRendererOpenInput,
  type RendererInterface,
  type RendererOpenResult,
  type RendererRenderResult
} from './interface'

export const chatSDKPostableMessageSchema = z.custom<PostableMessage>(() => true)

export const chatSDKMarkdownTextChunkSchema = z
  .object({
    type: z.literal('markdown_text'),
    text: z.string()
  })
  .strict()

export const chatSDKTaskUpdateChunkSchema = z
  .object({
    type: z.literal('task_update'),
    id: z.string(),
    title: z.string(),
    status: z.enum(['pending', 'in_progress', 'complete', 'error']),
    details: z.string().optional(),
    output: z.string().optional()
  })
  .strict()

export const chatSDKPlanUpdateChunkSchema = z
  .object({
    type: z.literal('plan_update'),
    title: z.string()
  })
  .strict()

export const chatSDKStreamChunkSchema = z.discriminatedUnion('type', [
  chatSDKMarkdownTextChunkSchema,
  chatSDKTaskUpdateChunkSchema,
  chatSDKPlanUpdateChunkSchema
])

export const chatSDKRendererMetadataSchema = z
  .object({
    sessionId: z.string(),
    title: z.string(),
    header: z.string().optional(),
    target: rendererTargetSchema,
    extra: rendererMetadataSchema.optional()
  })
  .strict()

export const chatSDKSessionOpenedOperationSchema = z
  .object({
    type: z.literal('chat.session.opened'),
    sessionId: z.string(),
    postable: chatSDKPostableMessageSchema,
    metadata: chatSDKRendererMetadataSchema
  })
  .strict()

export const chatSDKMessageUpsertOperationSchema = z
  .object({
    type: z.literal('chat.message.upsert'),
    sessionId: z.string(),
    postable: chatSDKPostableMessageSchema,
    metadata: chatSDKRendererMetadataSchema
  })
  .strict()

export const chatSDKStreamAppendOperationSchema = z
  .object({
    type: z.literal('chat.stream.append'),
    sessionId: z.string(),
    chunks: z.array(chatSDKStreamChunkSchema)
  })
  .strict()

export const chatSDKStatusUpdateOperationSchema = z
  .object({
    type: z.literal('chat.status.update'),
    sessionId: z.string(),
    status: z.string()
  })
  .strict()

export const chatSDKSessionClosedOperationSchema = z
  .object({
    type: z.literal('chat.session.closed'),
    sessionId: z.string(),
    postable: chatSDKPostableMessageSchema,
    metadata: chatSDKRendererMetadataSchema
  })
  .strict()

export const chatSDKOperationSchema = z.discriminatedUnion('type', [
  chatSDKSessionOpenedOperationSchema,
  chatSDKMessageUpsertOperationSchema,
  chatSDKStreamAppendOperationSchema,
  chatSDKStatusUpdateOperationSchema,
  chatSDKSessionClosedOperationSchema
])

export type ChatSDKPostableMessage = PostableMessage
export type ChatSDKMarkdownTextChunk = z.output<typeof chatSDKMarkdownTextChunkSchema>
export type ChatSDKTaskUpdateChunk = z.output<typeof chatSDKTaskUpdateChunkSchema>
export type ChatSDKPlanUpdateChunk = z.output<typeof chatSDKPlanUpdateChunkSchema>
export type ChatSDKStreamChunk = z.output<typeof chatSDKStreamChunkSchema>
export type ChatSDKRendererMetadata = z.output<typeof chatSDKRendererMetadataSchema>
export type ChatSDKOperation = z.output<typeof chatSDKOperationSchema>

type ChatSDKSessionState = {
  sessionId: string
  title: string
  header?: string
  target: RendererTarget
  metadata?: Record<string, unknown>
  text: string
  status?: string
  tasks: Map<string, RendererTask>
  planStarted: boolean
  done: boolean
}

export class ChatSDKRenderer implements RendererInterface<ChatSDKOperation[]> {
  readonly kind = 'chat-sdk'
  private readonly sessions = new Map<string, ChatSDKSessionState>()

  async open(input: RendererOpenInput): Promise<RendererOpenResult<ChatSDKOperation[]>> {
    const parsed = parseRendererOpenInput(input)
    const sessionId = parsed.sessionId ?? ulid()
    const state: ChatSDKSessionState = {
      sessionId,
      title: parsed.title,
      header: parsed.header?.trim() || undefined,
      target: parsed.target,
      metadata: parsed.metadata,
      text: '',
      tasks: new Map(),
      planStarted: false,
      done: false
    }
    this.sessions.set(sessionId, state)
    return {
      sessionId,
      output: [
        {
          type: 'chat.session.opened',
          sessionId,
          postable: postableForState(state),
          metadata: metadataForState(state)
        }
      ]
    }
  }

  async render(
    sessionId: string,
    event: RendererEvent
  ): Promise<RendererRenderResult<ChatSDKOperation[]>> {
    const parsed = parseRendererEvent(event)
    if (parsed.type === 'renderer.done') return this.close(sessionId, parsed)

    const state = this.requireSession(sessionId)
    if (parsed.type === 'renderer.status') {
      state.status = parsed.status
      return {
        output: [
          {
            type: 'chat.status.update',
            sessionId,
            status: parsed.status
          },
          upsertOperation(state)
        ]
      }
    }

    if (parsed.type === 'renderer.message.delta') {
      state.text += parsed.text
      return {
        output: [
          ...(parsed.text
            ? [
                {
                  type: 'chat.stream.append' as const,
                  sessionId,
                  chunks: [{ type: 'markdown_text' as const, text: parsed.text }]
                }
              ]
            : []),
          upsertOperation(state)
        ]
      }
    }

    if (parsed.type === 'renderer.message.snapshot') {
      state.text = parsed.text
      return { output: [upsertOperation(state)] }
    }

    state.tasks.set(parsed.task.id, parsed.task)
    const chunks = taskStreamChunks(state, parsed.task)
    return {
      output: [
        ...(chunks.length
          ? [
              {
                type: 'chat.stream.append' as const,
                sessionId,
                chunks
              }
            ]
          : []),
        upsertOperation(state)
      ]
    }
  }

  async close(
    sessionId: string,
    event: RendererDoneEvent = { type: 'renderer.done' }
  ): Promise<RendererRenderResult<ChatSDKOperation[]>> {
    const parsed = parseRendererDoneEvent(event)
    const state = this.requireSession(sessionId)
    if (parsed.finalText !== undefined) state.text = parsed.finalText
    if (parsed.error) {
      state.tasks.set('renderer-error', {
        id: 'renderer-error',
        title: parsed.error,
        status: 'error'
      })
    }
    state.status = parsed.isError ? 'Error' : ''
    state.done = true
    const postable = postableForState(state)
    const metadata = metadataForState(state)
    this.sessions.delete(sessionId)
    return {
      output: [
        {
          type: 'chat.message.upsert',
          sessionId,
          postable,
          metadata
        },
        {
          type: 'chat.session.closed',
          sessionId,
          postable,
          metadata
        }
      ]
    }
  }

  private requireSession(sessionId: string): ChatSDKSessionState {
    const state = this.sessions.get(sessionId)
    if (!state) throw new Error('renderer_session_not_found')
    return state
  }
}

function upsertOperation(state: ChatSDKSessionState): ChatSDKOperation {
  return {
    type: 'chat.message.upsert',
    sessionId: state.sessionId,
    postable: postableForState(state),
    metadata: metadataForState(state)
  }
}

function metadataForState(state: ChatSDKSessionState): ChatSDKRendererMetadata {
  return {
    sessionId: state.sessionId,
    title: state.title,
    header: state.header,
    target: state.target,
    extra: state.metadata
  }
}

function postableForState(state: ChatSDKSessionState): PostableMessage {
  return { ast: astForState(state) }
}

function astForState(state: ChatSDKSessionState): Root {
  const children: Content[] = []
  if (state.header) {
    children.push(paragraph([chatText(state.header)]))
  }
  if (state.status) {
    children.push(paragraph([strong([chatText('Status: ')]), chatText(state.status)]))
  }
  for (const task of state.tasks.values()) {
    children.push(...taskToAst(task))
  }
  if (state.text.trim()) {
    children.push(...parseMarkdown(state.text).children)
  }
  return root(children)
}

function taskToAst(task: RendererTask): Content[] {
  const children: Content[] = [
    paragraph([strong([chatText(`${task.status}: `)]), chatText(task.title)])
  ]
  if (task.details?.length) {
    children.push(paragraph([strong([chatText('Details')])]))
    children.push(...contentToAst(task.details))
  }
  if (task.output?.length) {
    children.push(paragraph([strong([chatText('Output')])]))
    children.push(...contentToAst(task.output))
  }
  return children
}

function contentToAst(content: RendererContent[]): Content[] {
  const children: Content[] = []
  let inline: Content[] = []
  const flushInline = () => {
    if (!inline.length) return
    children.push(paragraph(inline))
    inline = []
  }

  for (const part of content) {
    if (part.type === 'text') {
      inline.push(chatText(part.text))
    } else if (part.type === 'link') {
      inline.push(chatLink(part.url, [chatText(part.text ?? part.url)]))
    } else {
      flushInline()
      children.push(codeBlock(part.text, part.language))
    }
  }
  flushInline()
  return children
}

function taskStreamChunks(state: ChatSDKSessionState, task: RendererTask): StreamChunk[] {
  const chunks: StreamChunk[] = []
  if (!state.planStarted) {
    state.planStarted = true
    chunks.push({ type: 'plan_update', title: state.title })
  }
  chunks.push({
    type: 'task_update',
    id: task.id,
    title: task.title,
    status: task.status,
    ...(task.details?.length ? { details: rendererContentToMarkdown(task.details) } : {}),
    ...(task.output?.length ? { output: rendererContentToMarkdown(task.output) } : {})
  })
  return chunks
}

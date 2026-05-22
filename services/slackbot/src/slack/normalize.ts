import type { WebClient } from '@slack/web-api'
import type { AnyBlock } from '@slack/types'
import type {
  NormalizedPart,
  NormalizedSlackEvent,
  SlackEnvelope,
  SlackEnvelopeEvent,
  SlackMessageFile
} from './types'

type SlackThreadMessage = {
  type?: string
  subtype?: string
  user?: string
  bot_id?: string
  text?: string
  ts?: string
  blocks?: AnyBlock[]
  files?: SlackMessageFile[]
}

type SlackHistoryMessage = NonNullable<NormalizedSlackEvent['history_messages']>[number]

export async function normalizeSlackEnvelope(opts: {
  envelope: SlackEnvelope
  botUserId?: string
  client: WebClient
}): Promise<NormalizedSlackEvent | null> {
  if (opts.envelope.type !== 'event_callback') return null
  const event = opts.envelope.event
  if (!event || !isMessageLikeEvent(event)) return null
  if (event.type === 'message' && event.subtype === 'file_share') return null
  if (event.subtype && event.subtype !== 'file_share') return null
  if (!event.user || !event.channel || !event.ts) return null
  if (event.bot_id) return null

  const teamId = opts.envelope.team_id ?? event.team
  if (!teamId) return null

  const threadTs = event.thread_ts ?? event.ts
  const text = normalizeSlackText(event.text ?? '', opts.botUserId)
  const richText = normalizeRichTextBlocks(event.blocks)
  const parts: NormalizedPart[] = []
  const textPart = [richText, text].filter(Boolean).join('\n').trim()
  if (textPart) parts.push({ type: 'text', text: textPart })

  for (const file of event.files ?? []) {
    const part = await fetchSlackFilePart(opts.client, file)
    if (part) parts.push(part)
  }
  const isMention =
    event.type === 'app_mention' ||
    Boolean(opts.botUserId && (event.text ?? '').includes(`<@${opts.botUserId}>`))
  const historyMessages = isMention
    ? await collectThreadHistorySafely({
        client: opts.client,
        channel: event.channel,
        threadTs,
        currentTs: event.ts,
        teamId,
        botUserId: opts.botUserId
      })
    : []

  return {
    thread_key: `slack:${teamId}:${event.channel}:${threadTs}`,
    message_id: `slack:${teamId}:${event.channel}:${event.ts}`,
    team_id: teamId,
    recipient_team_id: recipientSlackTeamId(event) ?? teamId,
    user_id: event.user,
    channel_id: event.channel,
    thread_ts: threadTs,
    is_mention: isMention,
    parts,
    ...(historyMessages.length ? { history_messages: historyMessages } : {}),
    slack: {
      event_id: opts.envelope.event_id,
      event_ts: event.event_ts,
      message_ts: event.ts,
      enterprise_id: opts.envelope.enterprise_id,
      user_team: event.user_team,
      source_team: event.source_team
    }
  }
}

function recipientSlackTeamId(event: SlackEnvelopeEvent): string | undefined {
  for (const candidate of [event.user_team, event.source_team, event.team]) {
    if (typeof candidate === 'string' && candidate.trim()) return candidate.trim()
  }
  return undefined
}

function isMessageLikeEvent(event: SlackEnvelopeEvent): boolean {
  return event.type === 'message' || event.type === 'app_mention'
}

async function collectThreadHistorySafely(opts: {
  client: WebClient
  channel: string
  threadTs: string
  currentTs: string
  teamId: string
  botUserId?: string
}): Promise<SlackHistoryMessage[]> {
  try {
    return await collectThreadHistory(opts)
  } catch (error) {
    console.warn('slack_thread_history_collect_failed', {
      channel: opts.channel,
      thread_ts: opts.threadTs,
      error: error instanceof Error ? error.message : String(error)
    })
    return []
  }
}

async function collectThreadHistory(opts: {
  client: WebClient
  channel: string
  threadTs: string
  currentTs: string
  teamId: string
  botUserId?: string
}): Promise<SlackHistoryMessage[]> {
  if (opts.currentTs === opts.threadTs) return []
  const history: SlackHistoryMessage[] = []
  let cursor: string | undefined

  do {
    const response = await opts.client.conversations.replies({
      channel: opts.channel,
      ts: opts.threadTs,
      limit: 200,
      cursor
    })
    const messages = Array.isArray(response.messages) ? response.messages : []
    for (const raw of messages) {
      const message = raw as SlackThreadMessage
      if (!message.ts || compareSlackTs(message.ts, opts.currentTs) >= 0) continue
      const role = message.user === opts.botUserId ? 'assistant' : 'user'
      if (role === 'user' && (!message.user || message.bot_id)) continue
      if (message.subtype && message.subtype !== 'file_share') continue

      const parts = await partsFromSlackMessage(opts.client, message, opts.botUserId)
      if (!parts.length) continue
      history.push({
        message_id: `slack:${opts.teamId}:${opts.channel}:${message.ts}`,
        role,
        parts,
        user_id: message.user,
        metadata: { platform: 'slack', history_backfill: true }
      })
    }

    const nextCursor = response.response_metadata?.next_cursor
    cursor = typeof nextCursor === 'string' && nextCursor.trim() ? nextCursor : undefined
  } while (cursor)

  return history
}

async function partsFromSlackMessage(
  client: WebClient,
  message: SlackThreadMessage,
  botUserId?: string
): Promise<NormalizedPart[]> {
  const text = normalizeSlackText(message.text ?? '', botUserId)
  const richText = normalizeRichTextBlocks(message.blocks)
  const parts: NormalizedPart[] = []
  const textPart = [richText, text].filter(Boolean).join('\n').trim()
  if (textPart) parts.push({ type: 'text', text: textPart })

  for (const file of message.files ?? []) {
    const part = await fetchSlackFilePart(client, file)
    if (part) parts.push(part)
  }
  return parts
}

function compareSlackTs(a: string, b: string): number {
  const left = Number(a)
  const right = Number(b)
  if (Number.isFinite(left) && Number.isFinite(right)) return left - right
  return a.localeCompare(b)
}

export function normalizeSlackText(input: string, botUserId?: string): string {
  let text = input
  if (botUserId) text = text.replaceAll(`<@${botUserId}>`, '').trim()
  return text
    .replace(/<([a-z]+:\/\/[^>|]+)\|([^>]+)>/gi, '$2 ($1)')
    .replace(/<([a-z]+:\/\/[^>]+)>/gi, '$1')
    .replace(/<#([A-Z0-9]+)\|([^>]+)>/g, '#$2')
    .replace(/<#([A-Z0-9]+)>/g, '#$1')
    .replace(/<@([A-Z0-9]+)>/g, '@$1')
    .replace(/<!subteam\^([A-Z0-9]+)\|([^>]+)>/g, '@$2')
    .replace(/<!(channel|here|everyone)>/g, '@$1')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .trim()
}

function normalizeRichTextBlocks(blocks: AnyBlock[] | undefined): string {
  if (!Array.isArray(blocks)) return ''
  return blocks.map(normalizeBlock).filter(Boolean).join('\n').trim()
}

function normalizeBlock(block: AnyBlock): string {
  let record: Record<string, unknown>
  try {
    record = assertRecord(block)
  } catch {
    return ''
  }
  if (record.type === 'rich_text' && Array.isArray(record.elements)) {
    return record.elements.map(normalizeRichTextContainer).filter(Boolean).join('\n')
  }
  return ''
}

function normalizeRichTextContainer(container: unknown): string {
  let record: Record<string, unknown>
  try {
    record = assertRecord(container)
  } catch {
    return ''
  }
  if (record.type === 'rich_text_section' && Array.isArray(record.elements)) {
    return record.elements.map(normalizeRichTextElement).join('')
  }
  if (record.type === 'rich_text_list' && Array.isArray(record.elements)) {
    return record.elements.map(element => `- ${normalizeRichTextContainer(element)}`).join('\n')
  }
  if (record.type === 'rich_text_quote' && Array.isArray(record.elements)) {
    return record.elements.map(normalizeRichTextElement).join('')
  }
  if (record.type === 'rich_text_preformatted' && Array.isArray(record.elements)) {
    return record.elements.map(normalizeRichTextElement).join('')
  }
  return ''
}

function normalizeRichTextElement(element: unknown): string {
  let record: Record<string, unknown>
  try {
    record = assertRecord(element)
  } catch {
    return ''
  }
  switch (record.type) {
    case 'text':
      return typeof record.text === 'string' ? record.text : ''
    case 'link':
      return typeof record.text === 'string'
        ? `${record.text} (${stringField(record.url)})`
        : stringField(record.url)
    case 'user':
      return `@${stringField(record.user_id)}`
    case 'channel':
      return `#${stringField(record.channel_id)}`
    case 'emoji':
      return `:${stringField(record.name)}:`
    case 'broadcast':
      return `@${stringField(record.range)}`
    default:
      return ''
  }
}

async function fetchSlackFilePart(
  client: WebClient,
  file: SlackMessageFile
): Promise<NormalizedPart | null> {
  const url = file.url_private_download ?? file.url_private
  if (!url) return null
  const token = client.token
  if (!token) return null

  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!response.ok) {
    throw new Error(
      `Slack file fetch failed for ${file.id ?? file.name ?? 'unknown'}: ${response.status}`
    )
  }

  const bytes = new Uint8Array(await response.arrayBuffer())
  const mimeType =
    file.mimetype ?? response.headers.get('content-type') ?? 'application/octet-stream'
  const type = mimeType.startsWith('image/')
    ? 'image'
    : isDocumentMime(mimeType)
      ? 'document'
      : 'file'
  return {
    type,
    name: file.name ?? file.title ?? file.id ?? 'slack-file',
    mime_type: mimeType,
    size: file.size ?? bytes.byteLength,
    slack_file_id: file.id,
    source: {
      type: 'base64',
      media_type: mimeType,
      data: Buffer.from(bytes).toString('base64')
    }
  }
}

function isDocumentMime(mimeType: string): boolean {
  return (
    mimeType.startsWith('text/') ||
    mimeType === 'application/pdf' ||
    mimeType.includes('document') ||
    mimeType.includes('spreadsheet') ||
    mimeType.includes('presentation') ||
    mimeType.includes('json')
  )
}

function assertRecord(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('expected object')
  }
  return value as Record<string, unknown>
}

function stringField(value: unknown): string {
  try {
    return assertString(value)
  } catch {
    return ''
  }
}

function assertString(value: unknown): string {
  if (typeof value !== 'string') throw new Error('expected string')
  return value
}

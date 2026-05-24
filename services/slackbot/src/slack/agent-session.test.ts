import { describe, expect, it } from 'bun:test'
import {
  AgentSessionRenderer,
  configureAgentSessionChatSdk,
  withAgentSessionLock
} from './agent-session'

function installCaptureAdapter() {
  const streamed: any[] = []
  const adapter = {
    startTyping: async (threadId: string, status?: string) => {
      streamed.push({ type: 'typing', threadId, status })
    },
    stream: async (threadId: string, chunks: AsyncIterable<any>, options: any) => {
      streamed.push({ type: 'stream', threadId, options })
      for await (const chunk of chunks) streamed.push(chunk)
    }
  }
  configureAgentSessionChatSdk(adapter)
  return streamed
}

describe('AgentSessionRenderer', () => {
  it('renders agent sessions exclusively through the Chat SDK stream adapter', async () => {
    const streamed = installCaptureAdapter()
    const renderer = new AgentSessionRenderer()
    const { sessionId } = await renderer.open({
      channel: 'C123',
      parentTs: '1778866921.505479',
      recipientTeamId: 'T123',
      recipientUserId: 'U123',
      header: 'base · gpt-5'
    })

    await renderer.text(sessionId, 'Hello')
    await renderer.step(sessionId, { id: 's1', title: 'Run command', status: 'in_progress' })
    await renderer.done(sessionId, { answerMarkdown: 'Done' })

    expect(streamed[0]).toEqual({
      type: 'typing',
      threadId: 'slack:C123:1778866921.505479',
      status: 'Thinking...'
    })
    expect(streamed[1]).toEqual({
      type: 'stream',
      threadId: 'slack:C123:1778866921.505479',
      options: {
        recipientTeamId: 'T123',
        recipientUserId: 'U123',
        taskDisplayMode: 'plan'
      }
    })
    expect(streamed).toContainEqual({ type: 'markdown_text', text: '_base · gpt-5_\n\n' })
    expect(streamed).toContainEqual({ type: 'markdown_text', text: 'Hello' })
    expect(streamed).toContainEqual({
      type: 'task_update',
      id: 's1',
      title: 'Run command',
      status: 'in_progress',
      details: undefined,
      output: undefined
    })
    expect(streamed).not.toContainEqual({ type: 'markdown_text', text: 'Done' })
  })

  it('streams terminal text when no live answer was emitted', async () => {
    const streamed = installCaptureAdapter()
    const renderer = new AgentSessionRenderer()
    const { sessionId } = await renderer.open({
      channel: 'C123',
      parentTs: '1778866921.505480',
      recipientTeamId: 'T123',
      recipientUserId: 'U123'
    })

    await renderer.done(sessionId, { answerMarkdown: 'Final only' })

    expect(streamed).toContainEqual({ type: 'markdown_text', text: 'Final only' })
  })

  it('serializes operations for the same session', async () => {
    installCaptureAdapter()
    const renderer = new AgentSessionRenderer()
    const { sessionId } = await renderer.open({
      channel: 'C123',
      parentTs: '1778866921.505481',
      recipientTeamId: 'T123',
      recipientUserId: 'U123'
    })
    const seen: string[] = []

    await Promise.all([
      withAgentSessionLock(sessionId, async () => {
        await Promise.resolve()
        seen.push('first')
      }),
      withAgentSessionLock(sessionId, async () => {
        seen.push('second')
      })
    ])

    await renderer.done(sessionId)
    expect(seen).toEqual(['first', 'second'])
  })
})

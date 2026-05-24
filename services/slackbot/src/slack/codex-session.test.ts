import { describe, expect, it } from 'bun:test'
import { AgentSessionRenderer, configureAgentSessionChatSdk } from './agent-session'
import { CodexSessionRenderer } from './codex-session'

function installCaptureAdapter() {
  const streamed: any[] = []
  configureAgentSessionChatSdk({
    startTyping: async () => undefined,
    stream: async (_threadId: string, chunks: AsyncIterable<any>) => {
      for await (const chunk of chunks) streamed.push(chunk)
    }
  })
  return streamed
}

describe('CodexSessionRenderer', () => {
  it('streams terminal text through the Chat SDK session', async () => {
    const streamed = installCaptureAdapter()
    const { sessionId } = await new AgentSessionRenderer().open({
      channel: 'C123',
      parentTs: '1778866921.505479',
      recipientTeamId: 'T123',
      recipientUserId: 'U123'
    })
    const renderer = new CodexSessionRenderer()

    const result = await renderer.event(sessionId, {
      type: 'turn.completed',
      result: 'Done'
    })

    expect(result.done).toBe(true)
    expect(streamed).toContainEqual({ type: 'markdown_text', text: 'Done' })
  })

  it('ignores duplicate terminal events after completion', async () => {
    installCaptureAdapter()
    const { sessionId } = await new AgentSessionRenderer().open({
      channel: 'C123',
      parentTs: '1778866921.505480',
      recipientTeamId: 'T123',
      recipientUserId: 'U123'
    })
    const renderer = new CodexSessionRenderer()

    const first = await renderer.event(sessionId, { type: 'result', result: 'Done' })
    const second = await renderer.event(sessionId, { type: 'turn.done', result: 'Again' })

    expect(first.done).toBe(true)
    expect(second.done).toBe(true)
    expect(second.streamedAnswerChars).toBe(first.streamedAnswerChars)
  })
})

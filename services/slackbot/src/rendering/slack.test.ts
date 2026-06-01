import { describe, expect, it } from 'bun:test'
import { SlackChatSDKRenderer } from './slack'

describe('v2 SlackChatSDKRenderer', () => {
  it('layers Slack delivery above the ChatSDK renderer', async () => {
    const calls: Array<{ method: string; params: any }> = []
    const client = {
      assistant: {
        threads: {
          setStatus: async (params: any) => {
            calls.push({ method: 'assistant.threads.setStatus', params })
            return { ok: true }
          }
        }
      },
      chat: {
        startStream: async (params: any) => {
          calls.push({ method: 'chat.startStream', params })
          return { ok: true, ts: '1778866940.295499' }
        },
        appendStream: async (params: any) => {
          calls.push({ method: 'chat.appendStream', params })
          return { ok: true }
        },
        stopStream: async (params: any) => {
          calls.push({ method: 'chat.stopStream', params })
          return { ok: true }
        },
        update: async (params: any) => {
          calls.push({ method: 'chat.update', params })
          return { ok: true }
        }
      }
    }

    const renderer = new SlackChatSDKRenderer(client as any)
    const open = await renderer.open({
      type: 'renderer.session.open',
      title: 'Centaur execution',
      header: 'base - codex',
      target: {
        platform: 'slack',
        threadKey: 'slack:T123:C123:1778866921.505479',
        slack: {
          channel: 'C123',
          parentTs: '1778866921.505479',
          recipientTeamId: 'T123',
          recipientUserId: 'U123'
        }
      }
    })

    expect(open.output[0]).toMatchObject({
      type: 'slack.session.opened',
      sessionId: open.sessionId
    })
    expect(open.output[0]?.chat[0]?.type).toBe('chat.session.opened')

    const text = await renderer.render(open.sessionId, {
      type: 'renderer.message.delta',
      text: 'Hello.'
    })
    expect(text.output[0]).toMatchObject({
      type: 'slack.text.delta',
      acceptedChars: 6
    })

    const task = await renderer.render(open.sessionId, {
      type: 'renderer.task.update',
      task: {
        id: 'cmd-1',
        title: 'Run command',
        status: 'complete',
        details: [{ type: 'code', language: 'sh', text: 'pnpm test' }]
      }
    })
    expect(task.output[0]).toMatchObject({
      type: 'slack.task.updated',
      taskId: 'cmd-1'
    })

    const done = await renderer.close(open.sessionId, {
      type: 'renderer.done',
      finalText: 'Hello.'
    })
    expect(done.output[0]).toMatchObject({
      type: 'slack.session.closed',
      sessionId: open.sessionId
    })
    expect(done.output[0]?.chat.at(-1)?.type).toBe('chat.session.closed')

    const start = calls.find(call => call.method === 'chat.startStream')
    expect(start?.params.chunks).toContainEqual({
      type: 'markdown_text',
      text: '_base - codex_\n'
    })
    expect(start?.params.chunks).toContainEqual({
      type: 'markdown_text',
      text: 'Hello.'
    })

    const taskUpdates = calls
      .flatMap(call => call.params.chunks ?? [])
      .filter(chunk => chunk.type === 'task_update')
    expect(taskUpdates.at(-1)).toMatchObject({
      id: 'cmd-1',
      title: 'Run command',
      status: 'complete',
      details: '```sh\npnpm test\n```'
    })
    expect(calls.map(call => call.method)).toContain('chat.stopStream')
  })
})

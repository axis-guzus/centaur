import { describe, expect, it } from 'bun:test'
import { toPlainText, type Root } from 'chat'
import { ChatSDKRenderer, type ChatSDKOperation } from '../src/chat-sdk'
import { rendererEventSchema } from '../src/schema'

const target = {
  platform: 'test',
  threadKey: 'test:thread-1'
}

describe('v2 ChatSDKRenderer', () => {
  it('validates renderer events with zod', () => {
    expect(
      rendererEventSchema.safeParse({
        type: 'renderer.task.update',
        task: { id: 'cmd-1', title: 'Run command', status: 'complete' }
      }).success
    ).toBe(true)

    expect(
      rendererEventSchema.safeParse({
        type: 'renderer.task.update',
        task: { id: 'cmd-1', title: 'Run command', status: 'done' }
      }).success
    ).toBe(false)
  })

  it('maps renderer events into real Chat SDK postable messages and stream chunks', async () => {
    const renderer = new ChatSDKRenderer()
    const open = await renderer.open({
      type: 'renderer.session.open',
      title: 'Centaur execution',
      header: 'base - codex',
      target
    })

    expect(open.output[0]).toMatchObject({
      type: 'chat.session.opened',
      sessionId: open.sessionId
    })
    expect(postableText(operation(open.output, 'chat.session.opened')?.postable)).toContain(
      'base - codex'
    )

    const text = await renderer.render(open.sessionId, {
      type: 'renderer.message.delta',
      text: 'Hello'
    })
    expect(text.output.find(operation => operation.type === 'chat.stream.append')).toMatchObject({
      type: 'chat.stream.append',
      chunks: [{ type: 'markdown_text', text: 'Hello' }]
    })
    expect(postableText(upsertPostable(text.output))).toContain('Hello')

    const task = await renderer.render(open.sessionId, {
      type: 'renderer.task.update',
      task: {
        id: 'cmd-1',
        title: 'Run command',
        status: 'complete',
        details: [{ type: 'code', language: 'sh', text: 'pnpm test' }]
      }
    })
    expect(task.output.find(operation => operation.type === 'chat.stream.append')).toMatchObject({
      type: 'chat.stream.append',
      chunks: [
        { type: 'plan_update', title: 'Centaur execution' },
        {
          type: 'task_update',
          id: 'cmd-1',
          title: 'Run command',
          status: 'complete',
          details: '```sh\npnpm test\n```'
        }
      ]
    })
    expect(postableText(upsertPostable(task.output))).toContain('Run command')

    const done = await renderer.close(open.sessionId, {
      type: 'renderer.done',
      finalText: 'Final answer'
    })
    expect(postableText(operation(done.output, 'chat.session.closed')?.postable)).toContain(
      'Final answer'
    )
  })
})

function operation<T extends ChatSDKOperation['type']>(
  output: ChatSDKOperation[],
  type: T
): Extract<ChatSDKOperation, { type: T }> | undefined {
  return output.find((item): item is Extract<ChatSDKOperation, { type: T }> => item.type === type)
}

function upsertPostable(output: ChatSDKOperation[]): unknown {
  return operation(output, 'chat.message.upsert')?.postable
}

function postableText(postable: unknown): string {
  const ast = (postable as { ast?: Root } | undefined)?.ast
  expect(ast?.type).toBe('root')
  return toPlainText(ast as Root)
}

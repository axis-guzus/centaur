import { describe, expect, it } from 'bun:test'
import { Hono, type MiddlewareHandler } from 'hono'
import { registerRenderingV2Routes } from './routes'

type Variables = {
  slackRawBody: string
}

type RenderingV2TestResponse = {
  ok: boolean
  renderer?: string
  session_id: string
  output: Array<Record<string, unknown>>
}

describe('v2 rendering routes', () => {
  it('opens a Slack renderer session and accepts renderer events', async () => {
    const calls: Array<{ method: string; params: any }> = []
    const app = renderingTestApp(calls)

    const opened = await app.request('/api/v2/rendering/sessions', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
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
    })

    expect(opened.status).toBe(200)
    const openedBody = (await opened.json()) as RenderingV2TestResponse
    expect(openedBody).toMatchObject({
      ok: true,
      renderer: 'slack-chat-sdk'
    })
    expect(openedBody.output[0]).toMatchObject({
      type: 'slack.session.opened',
      sessionId: openedBody.session_id
    })

    const event = await app.request(`/api/v2/rendering/sessions/${openedBody.session_id}/events`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        type: 'renderer.message.delta',
        text: 'Hello.'
      })
    })
    expect(event.status).toBe(200)
    const eventBody = (await event.json()) as RenderingV2TestResponse
    expect(eventBody.output[0]).toMatchObject({
      type: 'slack.text.delta',
      acceptedChars: 6
    })

    const done = await app.request(`/api/v2/rendering/sessions/${openedBody.session_id}/events`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        type: 'renderer.done',
        finalText: 'Hello.'
      })
    })
    expect(done.status).toBe(200)
    const doneBody = (await done.json()) as RenderingV2TestResponse
    expect(doneBody.output[0]).toMatchObject({
      type: 'slack.session.closed',
      sessionId: openedBody.session_id
    })
    expect(calls.map(call => call.method)).toContain('chat.startStream')
    expect(calls.map(call => call.method)).toContain('chat.stopStream')
  })

  it('rejects malformed renderer payloads before calling Slack', async () => {
    const calls: Array<{ method: string; params: any }> = []
    const app = renderingTestApp(calls)

    const response = await app.request('/api/v2/rendering/sessions', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        type: 'renderer.session.open',
        target: { platform: 'slack' }
      })
    })

    expect(response.status).toBe(400)
    expect(await response.json()).toMatchObject({
      ok: false,
      error: 'invalid_renderer_payload'
    })
    expect(calls).toHaveLength(0)
  })
})

function renderingTestApp(calls: Array<{ method: string; params: any }>) {
  const app = new Hono<{ Variables: Variables }>()
  registerRenderingV2Routes(app, {
    apiKeyMiddleware: testApiKeyMiddleware,
    resolveClient: async () =>
      ({
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
      }) as any
  })
  return app
}

const testApiKeyMiddleware: MiddlewareHandler<{ Variables: Variables }> = async (c, next) => {
  if (c.req.header('authorization') !== 'Bearer test-key') {
    return c.json({ ok: false, error: 'unauthorized' }, 401)
  }
  await next()
}

function authHeaders(): HeadersInit {
  return {
    authorization: 'Bearer test-key',
    'content-type': 'application/json'
  }
}

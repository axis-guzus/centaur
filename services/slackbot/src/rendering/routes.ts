import { Hono, type Context, type MiddlewareHandler } from 'hono'
import type { WebClient } from '@slack/web-api'
import { rendererEventSchema } from '@centaur/rendering'
import { z } from 'zod'
import { SlackChatSDKRenderer, slackRendererOpenInputSchema } from './slack'

type RenderingRouteVariables = {
  slackRawBody: string
}

export type RenderingV2RouteDeps = {
  apiKeyMiddleware: MiddlewareHandler<{ Variables: RenderingRouteVariables }>
  resolveClient(): Promise<WebClient>
}

export function registerRenderingV2Routes(
  app: Hono<{ Variables: RenderingRouteVariables }>,
  deps: RenderingV2RouteDeps
): void {
  let renderer: SlackChatSDKRenderer | null = null

  const rendererFor = async (): Promise<SlackChatSDKRenderer> => {
    if (renderer) return renderer
    renderer = new SlackChatSDKRenderer(await deps.resolveClient())
    return renderer
  }

  app.post('/api/v2/rendering/sessions', deps.apiKeyMiddleware, async c => {
    try {
      const input = slackRendererOpenInputSchema.parse(await c.req.json())
      const activeRenderer = await rendererFor()
      const result = await activeRenderer.open(input)
      return c.json({
        ok: true,
        renderer: activeRenderer.kind,
        session_id: result.sessionId,
        output: result.output
      })
    } catch (error) {
      return rendererErrorResponse(c, error)
    }
  })

  app.post('/api/v2/rendering/sessions/:session_id/events', deps.apiKeyMiddleware, async c => {
    try {
      const sessionId = c.req.param('session_id')
      const event = rendererEventSchema.parse(await c.req.json())
      const activeRenderer = await rendererFor()
      const result =
        event.type === 'renderer.done'
          ? await activeRenderer.close(sessionId, event)
          : await activeRenderer.render(sessionId, event)
      return c.json({
        ok: true,
        renderer: activeRenderer.kind,
        session_id: sessionId,
        output: result.output
      })
    } catch (error) {
      return rendererErrorResponse(c, error)
    }
  })
}

function rendererErrorResponse(c: Context, error: unknown) {
  if (error instanceof z.ZodError) {
    return c.json(
      {
        ok: false,
        error: 'invalid_renderer_payload',
        issues: error.issues
      },
      400
    )
  }
  const data = (error as { data?: unknown })?.data
  if (data && typeof data === 'object') return c.json(data, 502)
  return c.json(
    {
      ok: false,
      error: error instanceof Error ? error.message : 'renderer_error'
    },
    502
  )
}

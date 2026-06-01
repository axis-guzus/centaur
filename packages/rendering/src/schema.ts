import { z } from 'zod'

export const rendererMetadataSchema = z.record(z.string(), z.unknown())

export const rendererTaskStatusSchema = z.enum(['pending', 'in_progress', 'complete', 'error'])

export const rendererTextContentSchema = z
  .object({
    type: z.literal('text'),
    text: z.string()
  })
  .strict()

export const rendererCodeContentSchema = z
  .object({
    type: z.literal('code'),
    text: z.string(),
    language: z.string().optional()
  })
  .strict()

export const rendererLinkContentSchema = z
  .object({
    type: z.literal('link'),
    url: z.string().min(1),
    text: z.string().optional()
  })
  .strict()

export const rendererContentSchema = z.discriminatedUnion('type', [
  rendererTextContentSchema,
  rendererCodeContentSchema,
  rendererLinkContentSchema
])

export const rendererTaskSchema = z
  .object({
    id: z.string().min(1),
    title: z.string().min(1),
    status: rendererTaskStatusSchema.default('in_progress'),
    details: z.array(rendererContentSchema).optional(),
    output: z.array(rendererContentSchema).optional(),
    metadata: rendererMetadataSchema.optional()
  })
  .strict()

export const rendererTargetSchema = z
  .object({
    platform: z.string().min(1),
    threadKey: z.string().optional(),
    surface: z.string().optional(),
    metadata: rendererMetadataSchema.optional()
  })
  .strict()

export const rendererOpenInputSchema = z
  .object({
    type: z.literal('renderer.session.open'),
    sessionId: z.string().min(1).optional(),
    title: z.string().min(1).default('Centaur execution'),
    header: z.string().optional(),
    target: rendererTargetSchema,
    metadata: rendererMetadataSchema.optional()
  })
  .strict()

export const rendererStatusEventSchema = z
  .object({
    type: z.literal('renderer.status'),
    status: z.string(),
    loadingMessages: z.array(z.string()).optional()
  })
  .strict()

export const rendererMessageDeltaEventSchema = z
  .object({
    type: z.literal('renderer.message.delta'),
    role: z.literal('assistant').default('assistant'),
    text: z.string(),
    flush: z.boolean().optional()
  })
  .strict()

export const rendererMessageSnapshotEventSchema = z
  .object({
    type: z.literal('renderer.message.snapshot'),
    role: z.literal('assistant').default('assistant'),
    text: z.string()
  })
  .strict()

export const rendererTaskUpdateEventSchema = z
  .object({
    type: z.literal('renderer.task.update'),
    task: rendererTaskSchema
  })
  .strict()

export const rendererDoneEventSchema = z
  .object({
    type: z.literal('renderer.done'),
    finalText: z.string().optional(),
    isError: z.boolean().optional(),
    error: z.string().optional()
  })
  .strict()

export const rendererEventSchema = z.discriminatedUnion('type', [
  rendererStatusEventSchema,
  rendererMessageDeltaEventSchema,
  rendererMessageSnapshotEventSchema,
  rendererTaskUpdateEventSchema,
  rendererDoneEventSchema
])

export const rendererInputSchema = z.discriminatedUnion('type', [
  rendererOpenInputSchema,
  rendererStatusEventSchema,
  rendererMessageDeltaEventSchema,
  rendererMessageSnapshotEventSchema,
  rendererTaskUpdateEventSchema,
  rendererDoneEventSchema
])

export type RendererMetadata = z.output<typeof rendererMetadataSchema>
export type RendererTaskStatus = z.output<typeof rendererTaskStatusSchema>
export type RendererContent = z.output<typeof rendererContentSchema>
export type RendererTask = z.output<typeof rendererTaskSchema>
export type RendererTarget = z.output<typeof rendererTargetSchema>
export type RendererOpenInput = z.input<typeof rendererOpenInputSchema>
export type ParsedRendererOpenInput = z.output<typeof rendererOpenInputSchema>
export type RendererStatusEvent = z.input<typeof rendererStatusEventSchema>
export type ParsedRendererStatusEvent = z.output<typeof rendererStatusEventSchema>
export type RendererMessageDeltaEvent = z.input<typeof rendererMessageDeltaEventSchema>
export type ParsedRendererMessageDeltaEvent = z.output<typeof rendererMessageDeltaEventSchema>
export type RendererMessageSnapshotEvent = z.input<typeof rendererMessageSnapshotEventSchema>
export type ParsedRendererMessageSnapshotEvent = z.output<typeof rendererMessageSnapshotEventSchema>
export type RendererTaskUpdateEvent = z.input<typeof rendererTaskUpdateEventSchema>
export type ParsedRendererTaskUpdateEvent = z.output<typeof rendererTaskUpdateEventSchema>
export type RendererDoneEvent = z.input<typeof rendererDoneEventSchema>
export type ParsedRendererDoneEvent = z.output<typeof rendererDoneEventSchema>
export type RendererEvent = z.input<typeof rendererEventSchema>
export type ParsedRendererEvent = z.output<typeof rendererEventSchema>
export type RendererInput = z.input<typeof rendererInputSchema>
export type ParsedRendererInput = z.output<typeof rendererInputSchema>

export function rendererContentToMarkdown(
  content: RendererContent[] | undefined
): string | undefined {
  if (!content?.length) return undefined
  return content
    .map(part => {
      if (part.type === 'text') return part.text
      if (part.type === 'link') return part.text ? `[${part.text}](${part.url})` : part.url
      const language = part.language ?? ''
      return `\`\`\`${language}\n${part.text}\n\`\`\``
    })
    .join('\n')
}

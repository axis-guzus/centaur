import {
  rendererDoneEventSchema,
  rendererEventSchema,
  rendererOpenInputSchema,
  type ParsedRendererDoneEvent,
  type ParsedRendererEvent,
  type ParsedRendererOpenInput,
  type RendererDoneEvent,
  type RendererEvent,
  type RendererOpenInput
} from './schema'

export type RendererOpenResult<TOutput> = {
  sessionId: string
  output: TOutput
}

export type RendererRenderResult<TOutput> = {
  output: TOutput
}

export interface RendererInterface<
  TOutput,
  TOpenInput = RendererOpenInput,
  TEvent = RendererEvent,
  TDoneEvent = RendererDoneEvent
> {
  readonly kind: string
  open(input: TOpenInput): Promise<RendererOpenResult<TOutput>>
  render(sessionId: string, event: TEvent): Promise<RendererRenderResult<TOutput>>
  close(sessionId: string, event?: TDoneEvent): Promise<RendererRenderResult<TOutput>>
}

export function parseRendererOpenInput(input: unknown): ParsedRendererOpenInput {
  return rendererOpenInputSchema.parse(input)
}

export function parseRendererEvent(input: unknown): ParsedRendererEvent {
  return rendererEventSchema.parse(input)
}

export function parseRendererDoneEvent(input: unknown): ParsedRendererDoneEvent {
  return rendererDoneEventSchema.parse(input)
}

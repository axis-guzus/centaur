import type { SlackEnvelope } from './types'

export type SlackOrgAuthorizationDecision = {
  ok: boolean
  externalTeamId?: string
  reason?: 'external_org_not_allowlisted'
}

export function authorizeSlackOrg(opts: {
  envelope: SlackEnvelope
  allowedExternalTeamIds: readonly string[]
}): SlackOrgAuthorizationDecision {
  const externalTeamId = externalSlackTeamId(opts.envelope)
  if (!externalTeamId) return { ok: true }

  const allowed = new Set(opts.allowedExternalTeamIds)
  if (allowed.has(externalTeamId)) return { ok: true, externalTeamId }

  return {
    ok: false,
    externalTeamId,
    reason: 'external_org_not_allowlisted'
  }
}

function externalSlackTeamId(envelope: SlackEnvelope): string | undefined {
  const homeTeamId = envelope.team_id
  const event = envelope.event
  if (!homeTeamId || !event) return undefined

  const candidates = [event.user_team, event.source_team, event.team]
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate && candidate !== homeTeamId) {
      return candidate
    }
  }
  return undefined
}

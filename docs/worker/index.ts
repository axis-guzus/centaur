/// <reference types="@cloudflare/workers-types" />

interface Env {
  ASSETS: Fetcher
  CONTACT_SUBMISSIONS?: D1Database
  DB?: D1Database
}

const createContactSubmissionsTable = `
  CREATE TABLE IF NOT EXISTS contact_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    company TEXT NOT NULL,
    role TEXT,
    use_case TEXT NOT NULL,
    wants_slack_invite INTEGER NOT NULL DEFAULT 0,
    user_agent TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
  )
`

function json(data: Record<string, unknown>, status = 200) {
  return Response.json(data, {
    status,
    headers: {
      'Cache-Control': 'no-store',
    },
  })
}

function isEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url)

    if (url.pathname === '/api/contact' && request.method === 'POST') {
      return handleContactSubmission(request, env)
    }

    if (url.pathname.startsWith('/api/')) {
      return json({ error: 'Not found' }, 404)
    }

    return env.ASSETS.fetch(request)
  },
} satisfies ExportedHandler<Env>

async function handleContactSubmission(request: Request, env: Env) {
  const db = env.CONTACT_SUBMISSIONS ?? env.DB
  if (!db) return json({ error: 'Contact storage is not configured' }, 500)

  const body = (await request.json().catch(() => null)) as
    | {
        name?: unknown
        email?: unknown
        company?: unknown
        role?: unknown
        useCase?: unknown
        wantsSlackInvite?: unknown
      }
    | null

  const name = typeof body?.name === 'string' ? body.name.trim() : ''
  const email = typeof body?.email === 'string' ? body.email.trim().toLowerCase() : ''
  const company = typeof body?.company === 'string' ? body.company.trim() : ''
  const role = typeof body?.role === 'string' ? body.role.trim() : ''
  const useCase = typeof body?.useCase === 'string' ? body.useCase.trim() : ''
  const wantsSlackInvite =
    body?.wantsSlackInvite === true || body?.wantsSlackInvite === 'true'

  if (!name) return json({ error: 'Name is required' }, 400)
  if (!isEmail(email)) return json({ error: 'Valid email is required' }, 400)
  if (!company) return json({ error: 'Company is required' }, 400)
  if (!useCase) return json({ error: 'Please share what you want to build' }, 400)

  await db.prepare(createContactSubmissionsTable).run()
  await db
    .prepare(
      `
        INSERT INTO contact_submissions (
          email,
          name,
          company,
          role,
          use_case,
          wants_slack_invite,
          user_agent,
          updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(email) DO UPDATE SET
          name = excluded.name,
          company = excluded.company,
          role = excluded.role,
          use_case = excluded.use_case,
          wants_slack_invite = excluded.wants_slack_invite,
          user_agent = excluded.user_agent,
          updated_at = datetime('now')
      `,
    )
    .bind(
      email,
      name,
      company,
      role || null,
      useCase,
      wantsSlackInvite ? 1 : 0,
      request.headers.get('user-agent'),
    )
    .run()

  return json({ ok: true })
}

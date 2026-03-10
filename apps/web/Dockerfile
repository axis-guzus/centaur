FROM node:22-slim AS base

RUN corepack enable pnpm

WORKDIR /app

# Install dependencies (cached independently of source changes)
COPY apps/web/package.json apps/web/pnpm-lock.yaml* ./
COPY apps/web/patches/ patches/
RUN pnpm install --frozen-lockfile 2>/dev/null || pnpm install

# Copy source and build
FROM base AS builder
COPY apps/web/ .
RUN pnpm build

# Production
FROM node:22-slim AS runner
RUN apt-get update && apt-get install -y --no-install-recommends curl jq && rm -rf /var/lib/apt/lists/*
WORKDIR /app

ENV NODE_ENV=production

# Next.js standalone output includes everything needed
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY scripts/bootstrap-secrets.sh /app/bootstrap-secrets.sh
COPY apps/web/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh /app/bootstrap-secrets.sh

EXPOSE 3001
ENV PORT=3001
ENV HOSTNAME="0.0.0.0"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["node", "server.js"]

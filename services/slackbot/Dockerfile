ARG NODEJS_IMAGE="node:24.15.0-bookworm-slim@sha256:03eae3ef7e88a9de535496fb488d67e02b9d96a063a8967bae657744ecd513f2"

FROM ${NODEJS_IMAGE} AS base

RUN corepack enable pnpm

WORKDIR /app

# Copy workspace root config + shared packages + this service
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml* ./
COPY packages/ packages/
COPY services/slackbot/package.json services/slackbot/
RUN cd services/slackbot && pnpm install --frozen-lockfile

# Copy source and build
FROM base AS builder
COPY services/slackbot/ services/slackbot/
RUN cd services/slackbot && pnpm build

# Production
FROM ${NODEJS_IMAGE} AS runner
RUN apt-get update && apt-get install -y --no-install-recommends curl jq && rm -rf /var/lib/apt/lists/*
WORKDIR /app

ENV NODE_ENV=production

# Next.js standalone output includes everything needed
COPY --from=builder /app/services/slackbot/.next/standalone ./
COPY --from=builder /app/services/slackbot/.next/static ./services/slackbot/.next/static
COPY services/slackbot/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 3001
ENV PORT=3001
ENV HOSTNAME="0.0.0.0"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["node", "services/slackbot/server.js"]

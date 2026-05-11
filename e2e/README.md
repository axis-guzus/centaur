# Centaur E2E Tests

This directory contains service-neutral system tests for the Centaur stack.
The tests talk to a real API deployment, which creates real sandbox pods and
drives a real harness. They intentionally do not live under `services/api` or
`services/slackbot` because they validate product-level behavior across
multiple services.

## Run against an existing local stack

Bring Centaur up first, then run the E2E package:

```bash
just up
pnpm install
CENTAUR_API_URL=http://localhost:8000 \
SLACKBOT_API_KEY=<your-local-slackbot-api-key> \
pnpm --filter @centaur/e2e test
```

If the API is only reachable from inside Kubernetes, port-forward it first:

```bash
kubectl port-forward -n centaur deploy/centaur-centaur-api 8000:8000
```

## Run in kind

The easiest local end-to-end path is to let the helper create or reuse a kind
cluster, deploy Centaur when needed, warm one sandbox, then run the tests. The
helper automatically loads environment variables from the repo-root `.env`
file, so a local `.env` containing `AMP_API_KEY=...` is enough:

```bash
e2e/deploy/run-kind.sh
```

Local runs are optimized for a fast feedback loop: by default they keep and
reuse the kind cluster, skip image builds, skip image loading unless the cluster
was just created, and skip Helm deploys when the release already exists. CI uses
the same script with cold defaults: recreate the cluster, build/load images,
deploy, run tests, and delete the cluster.

Useful options:

```bash
# Force a full local rebuild + image reload + deploy
E2E_BUILD=1 CENTAUR_E2E_LOAD_IMAGES=1 CENTAUR_E2E_DEPLOY=1 e2e/deploy/run-kind.sh

# Recreate the kind cluster for a clean local run
CENTAUR_E2E_RECREATE_CLUSTER=1 e2e/deploy/run-kind.sh

# Delete the cluster after the run
CENTAUR_E2E_KEEP_CLUSTER=0 e2e/deploy/run-kind.sh

# Skip waiting for warm sandboxes
CENTAUR_E2E_WARM_POOL_TARGET=0 e2e/deploy/run-kind.sh

# Use a different kind cluster name
CENTAUR_E2E_KIND_CLUSTER=my-centaur-e2e e2e/deploy/run-kind.sh
```

## CI

`.github/workflows/e2e-amp.yml` runs the same tests in kind. It requires the
GitHub Actions secret `AMP_API_KEY`.

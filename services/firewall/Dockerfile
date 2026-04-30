FROM mitmproxy/mitmproxy:11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl jq && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /certs && chown mitmproxy:mitmproxy /certs
RUN pip install --no-cache-dir rich structlog
USER mitmproxy

COPY centaur_sdk /app/centaur_sdk
COPY services/firewall/addon.py /app/addon.py
COPY services/firewall/classification.py /app/classification.py
COPY --chmod=755 services/firewall/entrypoint.sh /entrypoint.sh

EXPOSE 8080 8081

ENTRYPOINT ["/entrypoint.sh"]

FROM edoburu/pgbouncer:latest

USER root
RUN apk add --no-cache curl jq
USER postgres

COPY --chmod=755 entrypoint.sh /custom-entrypoint.sh

ENTRYPOINT ["/custom-entrypoint.sh"]
CMD ["/usr/bin/pgbouncer", "/etc/pgbouncer/pgbouncer.ini"]

FROM edoburu/pgbouncer:latest@sha256:85d1e38593617af1b5f7f285e97d407e56c29939683cc7cfe4c8f6dc19f1268b

USER root
RUN apk add --no-cache bash
COPY services/pgbouncer/entrypoint.sh /custom-entrypoint.sh
RUN chmod +x /custom-entrypoint.sh
USER postgres

ENTRYPOINT ["/custom-entrypoint.sh"]
CMD ["/usr/bin/pgbouncer", "/etc/pgbouncer/pgbouncer.ini"]

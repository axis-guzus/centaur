FROM nginx:1.27-alpine

RUN rm -f /etc/nginx/conf.d/default.conf

COPY services/nginx/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

FROM python:3.11-alpine
RUN apk add --no-cache curl jq bash
RUN pip install --no-cache-dir starlette uvicorn[standard] python-multipart rich
COPY centaur_sdk /app/centaur_sdk
COPY services/auth/main.py /app/main.py
COPY scripts/bootstrap-secrets.sh /app/bootstrap-secrets.sh
COPY services/auth/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh /app/bootstrap-secrets.sh
WORKDIR /app
EXPOSE 4000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "4000"]

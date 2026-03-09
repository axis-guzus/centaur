FROM python:3.11-alpine
RUN pip install --no-cache-dir starlette uvicorn[standard] python-multipart
COPY main.py /app/main.py
COPY --chmod=755 entrypoint.sh /entrypoint.sh
WORKDIR /app
EXPOSE 4000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "4000"]

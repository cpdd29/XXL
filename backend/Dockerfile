FROM hermes-agent:local AS node_runtime

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY --from=node_runtime /usr/bin/node /usr/bin/node
COPY --from=node_runtime /usr/share/nodejs /usr/share/nodejs
COPY --from=node_runtime /lib/aarch64-linux-gnu /lib/aarch64-linux-gnu
RUN ln -sf /usr/share/nodejs/npm/bin/npm-cli.js /usr/bin/npm \
    && mkdir -p /usr/local/lib/node_modules

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Install local executor runtimes for validation inside the containerized backend.
RUN npm install -g @openai/codex @anthropic-ai/claude-code

COPY app ./app

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

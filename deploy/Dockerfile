# Assertify Cloud: the public MCP relay at https://mcp.assertify.co/mcp (no browser runs here).
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable && rm -rf /root/.cache
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
RUN useradd -r -u 10001 assertify && mkdir -p /data && chown assertify /data
USER assertify
EXPOSE 8080
CMD ["assertify", "cloud", "--port", "8080"]

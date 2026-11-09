# Assertify demo computer for app reviewers: the fake "Northwind Mail" site plus `assertify connect`.
# It links to the hosted server like any computer; reviewers reach it with the reviewer passphrase.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable && rm -rf /root/.cache
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/* /root/.cache
RUN useradd -r -m -u 10001 assertify && mkdir -p /data && chown assertify /data
USER assertify
CMD ["assertify", "demo"]

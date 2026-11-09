# Hosting Assertify Cloud

Assertify Cloud is the public MCP server at `https://mcp.assertify.co/mcp` that the Claude and OpenAI
plugin directories point to. It relays tool calls to `assertify connect` on each user's computer;
no browser runs on the server. Code: [`src/assertify/cloud.py`](../src/assertify/cloud.py).

It runs as **one** machine: connected computers hold WebSockets to it and that state is in memory.
The SQLite database (app registrations, computer IDs, hashed tokens) lives on a volume.

## First deploy (Fly.io)

```
fly apps create assertify
fly volumes create assertify_data --size 1 --region iad
fly deploy
fly certs add mcp.assertify.co
```

`fly certs add` prints the DNS records to add at your domain registrar (a `CNAME` record for `mcp`). Once the certificate is issued, check:

```
curl https://mcp.assertify.co/healthz
curl https://mcp.assertify.co/.well-known/oauth-authorization-server
```

## OpenAI domain verification

The OpenAI portal gives you a token to serve at `/.well-known/openai-apps-challenge`:

```
fly secrets set OPENAI_APPS_CHALLENGE=<token from the portal>
```

## Updates

`fly deploy` from the repo root. Connected computers reconnect by themselves within a minute.

## Running it locally

```
ASSERTIFY_CLOUD_URL=http://127.0.0.1:8080 ASSERTIFY_CLOUD_DB=./cloud.db assertify cloud --host 127.0.0.1
ASSERTIFY_CLOUD_URL=http://127.0.0.1:8080 assertify connect
```

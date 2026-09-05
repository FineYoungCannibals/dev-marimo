# dev-marimo

A self-hosted [marimo](https://marimo.io) notebook server, run in Docker. Dev
and prod use the same image and the same layout so the experience matches in
both places.

## Layout

- `notebooks/` — your marimo notebooks. `notebooks/utils` is on `PYTHONPATH`
  inside the container, so modules there are importable from any notebook.
- `.marimo.toml` — marimo's own app config (theme, AI providers, keymap,
  etc.), bind-mounted into the container so it survives rebuilds/redeploys.
- `.env` — environment variables available to notebooks via `os.environ`,
  plus `MARIMO_HOST`/`MARIMO_PORT`.

## First-time setup (dev)

1. `cp .env_template .env` and fill in values.
2. `cp .marimo.toml.example .marimo.toml` and adjust as you like (AI
   provider, theme, etc.). This file is gitignored — it's local config, not
   code.
3. `docker compose up --build`
4. Open `http://localhost:2718`.

Both files must exist **before** `docker compose up`, since Docker will
create an empty directory (not a file) at the mount target if the host path
doesn't exist yet, which breaks marimo's config loading.

## Config persistence

marimo reads its settings from `.marimo.toml`, searching from the working
directory upward and finally falling back to `~/.marimo.toml` in the
container's home directory. We bind-mount a single file there
(`/home/app_user/.marimo.toml`) rather than mounting a whole directory —
that's the one path marimo treats as a trusted, user-owned config location
(as opposed to, say, a `.marimo.toml` that happened to live inside a cloned
notebook repo), and it's simpler to reason about than a directory of
generated files.

A plain bind mount is fine for this — no need for a named volume. The only
requirement is that the file exists on the host before the container starts.

## Prod (Portainer)

`docker-compose.prod.yml` expects, on the host running the stack:

- `/opt/docker/marimo/.env` — same shape as `.env_template`.
- `/opt/docker/marimo/.marimo.toml` — copy of `.marimo.toml.example`,
  adjusted for the deployment.
- `/opt/docker/marimo/dev_notebooks/` — your notebooks (may already contain
  a `utils/` subfolder).

Create these on the host before deploying the stack, for the same reason as
above. Once created, they persist across redeploys/image updates
automatically.

Auth is handled by Authentik at the Traefik layer (see the
`traefik.http.routers.marimortr.middlewares=authentik@docker` label), which
is why marimo itself runs with `--no-token`.

## AI assistant (lemonade)

marimo's AI assistant is wired up as a custom OpenAI-compatible provider
pointed at the local lemonade server, via `.marimo.toml`:

```toml
[ai.custom_providers.lemonade]
base_url = "http://<lemonade-host>:8000/api/v1"
api_key = "not-needed"

[ai.models]
chat_model = "lemonade/<your-chat-model>"
```

Update the model name(s) if what's loaded on the lemonade server changes.

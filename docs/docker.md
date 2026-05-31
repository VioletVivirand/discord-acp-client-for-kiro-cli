# Running in Docker

Run the bot in an isolated container so Discord users can drive Kiro to execute
commands without touching your host. The container is the security boundary: it
runs as a non-root user, drops all Linux capabilities, forbids privilege
escalation, and mounts **no** Docker socket or host secrets.

## What's in the image

- **Base:** `ubuntu:26.04`.
- **User:** non-root `bot` (UID/GID `1000`, configurable via build args).
- **Python:** 3.14, provided by [`uv`](https://docs.astral.sh/uv/) (independent of the OS Python).
- **`kiro-cli`:** installed to `~/.local/bin` (architecture-aware: x86_64 / aarch64).
- **Homebrew:** bundled, so the `bot` user (and Kiro's agents) can `brew install`
  extra tooling at runtime **without root or sudo**.

## Quick start

The commands below are plain `docker` invocations — run them from the repo root.
A [`docker compose`](#using-docker-compose) alternative is documented at the end.

**1. Configure** — copy the env template and set your token:

```bash
cp .env.example .env          # set DISCORD_TOKEN
```

**2. Build the image:**

```bash
docker build -t discord-acp-kiro-bot:latest .
```

**3. Create the named volume** (auth/config/sessions + workspace):

```bash
docker volume create discord-acp-kiro-data
```

**4. Start the bot** (detached, locked down, auto-restart):

```bash
docker run -d \
    --name discord-acp-kiro-bot \
    --env-file .env \
    --restart unless-stopped \
    --security-opt no-new-privileges \
    --cap-drop ALL \
    -v discord-acp-kiro-data:/home/bot/.kiro \
    discord-acp-kiro-bot:latest
```

**5. Authenticate Kiro** (one-time, see [below](#authentication-one-time-persists-on-a-volume)):

```bash
docker exec -it discord-acp-kiro-bot kiro-cli login --use-device-flow
```

**6. Follow the logs:**

```bash
docker logs -f discord-acp-kiro-bot
```

### Managing the container

```bash
docker exec -it discord-acp-kiro-bot bash -l   # interactive shell
docker stop discord-acp-kiro-bot               # stop
docker start discord-acp-kiro-bot              # start again
docker restart discord-acp-kiro-bot            # restart
docker rm -f discord-acp-kiro-bot              # remove
```

## Authentication (one-time, persists on a volume)

Kiro must be authenticated inside the container. The credential store lives in
the `discord-acp-kiro-data` volume, so you log in **once** and it survives restarts.

Use the **device flow** — it shows a URL and a one-time code; no browser is
needed inside the container:

```bash
docker exec -it discord-acp-kiro-bot kiro-cli login --use-device-flow
```

1. Pick a sign-in method (Builder ID, Google, GitHub, or your organization).
2. Open the printed URL in any browser (laptop, phone, …) and enter the code.
3. The CLI detects success automatically and writes the token to the volume.

After logging in, if you had already messaged the bot, click the **Retry**
button in Discord to resend your message.

### Alternative: API key (headless, no interactive login)

For Kiro Pro/Pro+/Power subscribers, set an API key in `.env` instead of the
device flow:

```dotenv
KIRO_API_KEY=ksk_xxxxxxxx
```

## Installing extra packages

The image ships two package managers:

- **Homebrew** (no sudo) — preferred for the runtime user and agents:
  ```bash
  docker exec -it discord-acp-kiro-bot bash -l
  brew install ripgrep jq
  ```
  Brew packages persist only for the container's lifetime (they live outside the
  mounted volumes); reinstall after recreating the container, or add them to the
  `Dockerfile` to bake them in.
- **apt** (build time only) — the `bot` user has no sudo by default. Add system
  packages by editing the `apt-get install` line in the `Dockerfile` and
  rebuilding.

## Persistence

One named volume holds everything:

| Volume | Mount | Contents |
| --- | --- | --- |
| `discord-acp-kiro-data` | `/home/bot/.kiro` | Kiro auth (`share/kiro-cli/data.sqlite3`), settings, agents, sessions, `bot.log`, and the `workspace/` subdirectory (`KIRO_SESSION_CWD` — files Kiro reads/writes) |

`XDG_DATA_HOME` is set to `/home/bot/.kiro/share` and `KIRO_SESSION_CWD` to
`/home/bot/.kiro/workspace`, so credential store, config, sessions, and the
workspace all nest under the single home volume.

## Security model

- Runs as non-root `bot`; never root.
- `--security-opt no-new-privileges` and `--cap-drop ALL`.
- No Docker socket and no host bind mounts — Kiro operates only inside the
  container and its volumes.
- The root filesystem is **not** read-only because runtime `brew install` needs
  to write to `/home/linuxbrew`.
- Discord users can make Kiro run arbitrary commands; the container isolation is
  the mitigation. Only invite the bot to servers/channels you trust, and keep
  **Public Bot** disabled (see the main README).

## Configuration build args

```bash
docker build --build-arg UID=1001 --build-arg GID=1001 \
             --build-arg PYTHON_VERSION=3.14 -t discord-acp-kiro-bot:latest .
```

For multi-architecture builds, `docker buildx` sets `TARGETARCH` automatically
(`amd64` → x86_64, `arm64` → aarch64).

## Using docker compose

`docker-compose.yml` wraps the same image, volumes, and security options:

```bash
cp .env.example .env                                        # set DISCORD_TOKEN
docker compose build
docker compose up -d
docker compose exec bot kiro-cli login --use-device-flow    # one-time Kiro auth
docker compose logs -f
docker compose down                                         # stop & remove
```

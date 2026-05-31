# syntax=docker/dockerfile:1
#
# Discord ACP Client for Kiro CLI — container image.
#
# Runs the bot as a non-root user ("bot"), with kiro-cli, a uv-managed
# Python 3.14, and Homebrew baked in so agents can install packages
# without root. The container is the security boundary: Discord users can
# drive Kiro to run arbitrary commands, so it never runs as root and ships
# with no Docker socket or host-secret access.

FROM ubuntu:26.04

# --- Build-time configuration -------------------------------------------------
ARG UID=1000
ARG GID=1000
ARG PYTHON_VERSION=3.14
# TARGETARCH is provided automatically by BuildKit (amd64 / arm64).
ARG TARGETARCH

ENV DEBIAN_FRONTEND=noninteractive

# --- System dependencies (apt, build time) -----------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        unzip \
        ca-certificates \
        git \
        build-essential \
        procps \
        locales \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# uv: fast Python/dependency manager (provides Python 3.14, decoupled from the OS).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# --- Non-root "bot" user ------------------------------------------------------
# ubuntu:26.04 ships a default "ubuntu" user at UID 1000; remove it so we can
# claim UID/GID 1000 for "bot".
RUN userdel -r ubuntu 2>/dev/null || true; \
    groupadd -g "${GID}" bot 2>/dev/null || groupmod -n bot "$(getent group "${GID}" | cut -d: -f1)"; \
    useradd -m -u "${UID}" -g "${GID}" -s /bin/bash bot

# Directories owned by bot: Homebrew prefix, Kiro home (with nested workspace), app.
RUN mkdir -p /home/linuxbrew /home/bot/.kiro/workspace /app \
    && chown -R bot:bot /home/linuxbrew /home/bot/.kiro /app

USER bot
ENV HOME=/home/bot
ENV PATH=/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:/home/bot/.local/bin:${PATH}

# --- Homebrew (bundled at build time, installed as the bot user, no sudo) -----
# Clone install into the standard Linux prefix so bottles work; this avoids the
# sudo the official installer would otherwise need to create /home/linuxbrew.
RUN git clone --depth=1 https://github.com/Homebrew/brew \
        /home/linuxbrew/.linuxbrew/Homebrew \
    && mkdir -p /home/linuxbrew/.linuxbrew/bin \
    && ln -s ../Homebrew/bin/brew /home/linuxbrew/.linuxbrew/bin/brew \
    && brew --version
ENV HOMEBREW_PREFIX=/home/linuxbrew/.linuxbrew \
    HOMEBREW_CELLAR=/home/linuxbrew/.linuxbrew/Cellar \
    HOMEBREW_REPOSITORY=/home/linuxbrew/.linuxbrew/Homebrew \
    HOMEBREW_NO_AUTO_UPDATE=1
# Make brew available in interactive (exec) shells too.
RUN echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> /home/bot/.bashrc \
    && echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> /home/bot/.profile

# --- kiro-cli (arch-aware zip installer -> ~/.local/bin) ----------------------
RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "$arch" in \
        amd64) karch=x86_64 ;; \
        arm64) karch=aarch64 ;; \
        *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    curl --proto '=https' --tlsv1.2 -fsSL \
        "https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-${karch}-linux.zip" \
        -o /tmp/kirocli.zip; \
    unzip -q /tmp/kirocli.zip -d /tmp; \
    /tmp/kirocli/install.sh --no-confirm; \
    rm -rf /tmp/kirocli /tmp/kirocli.zip; \
    kiro-cli --version

# --- Python dependencies (uv-managed Python 3.14) -----------------------------
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_INSTALL_DIR=/home/bot/.local/share/uv/python

RUN uv python install "${PYTHON_VERSION}"

# Dependency layer (cached unless pyproject/uv.lock change).
COPY --chown=bot:bot pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Project source + install.
COPY --chown=bot:bot src ./src
RUN uv sync --frozen

# --- Runtime configuration ----------------------------------------------------
# kiro-cli keeps settings under KIRO_HOME but its credential/session store
# (data.sqlite3) lives in $XDG_DATA_HOME/kiro-cli. Point XDG_DATA_HOME inside
# KIRO_HOME and nest the workspace there too, so a single volume persists
# auth + config + sessions + workspace.
ENV KIRO_HOME=/home/bot/.kiro \
    XDG_DATA_HOME=/home/bot/.kiro/share \
    KIRO_SESSION_CWD=/home/bot/.kiro/workspace \
    KIRO_CLI_BIN=kiro-cli \
    LOG_FILE=/home/bot/.kiro/bot.log

# Persisted: Kiro auth/config/sessions and the nested workspace (single volume).
VOLUME ["/home/bot/.kiro"]

CMD ["uv", "run", "--no-sync", "discord-acp-kiro-bot"]

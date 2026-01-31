FROM python:3.14-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.4.20 /uv /usr/local/bin/uv
ENV VIRTUAL_ENV=/home/app_user/venv
ENV UV_PROJECT_ENVIRONMENT=$VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN apt update && \
    apt upgrade -y && \
    apt install -y curl iputils-ping jq && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m app_user

FROM base AS builder
USER app_user
WORKDIR /home/app_user/app
COPY --chown=app_user:app_user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM base AS runtime
USER app_user

COPY --from=builder --chown=app_user:app_user $VIRTUAL_ENV $VIRTUAL_ENV

# Create notebook directory, copy utils into it, and make it serve modules
RUN mkdir -p /home/app_user/notebooks/utils /home/app_user/app

# Set PYTHONPATH so Python can find modules in /home/app_user/notebooks/utils
ENV PYTHONPATH="/home/app_user/notebooks/utils:${PYTHONPATH}"

COPY --chown=app_user:app_user pyproject.toml uv.lock /home/app_user/app/

# Copy the entrypoint script.
COPY --chown=app_user:app_user entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /home/app_user/notebooks
EXPOSE 2718

# Use the entrypoint script to update dependencies upon container rebuilds
ENTRYPOINT ["/entrypoint.sh"]
# CMD ["marimo", "edit", "--host", "0.0.0.0", "--port", "2718"]

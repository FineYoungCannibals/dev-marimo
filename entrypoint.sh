#!/bin/sh
set -e

# Activate the virtual environment if needed.
# If the PATH is already set properly, this might be unnecessary,
# but it ensures that any activation-specific shell modifications are applied.
. "$VIRTUAL_ENV/bin/activate"

APP_DIR="/home/app_user/app"
NOTEBOOK_DIR="/home/app_user/app/notebooks"
MARIMO_CONFIG="/home/app_user/.marimo.toml"

# Install or update dependencies at startup.
if [ -f "$APP_DIR/pyproject.toml" ]; then
  echo "Installing/updating Python dependencies..."
  cd "$APP_DIR"
  uv sync --frozen --no-dev --no-install-project
  cd "$NOTEBOOK_DIR"  # switch back to notebook directory after installation
fi

# Refresh the lemonade model list in .marimo.toml. Best-effort: if lemonade
# is unreachable at startup, keep whatever model list is already there
# rather than blocking the container from coming up.
if [ -f "$MARIMO_CONFIG" ]; then
  echo "Refreshing lemonade model list..."
  python "$APP_DIR/scripts/refresh_ai_models.py" \
    --config "$MARIMO_CONFIG" --provider lemonade --update-chat-model \
    || echo "Warning: could not refresh lemonade models, continuing with existing config."
fi

# TODO(mcp-2-migration): remove once marimo ships a release including
# commit 849f16b6d ("feat(mcp): migrate to MCP 2 (#10581)") -- see
# scripts/sitecustomize.py for details.
export PYTHONPATH="$APP_DIR/scripts${PYTHONPATH:+:$PYTHONPATH}"

# Execute the main command passed via CMD.
exec "$@"

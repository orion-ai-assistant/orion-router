#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-docker}"

echo "=========================================="
echo "      Orion Router Native Installer       "
echo "=========================================="

if [ "$MODE" != "local" ] && [ "$MODE" != "docker" ]; then
  echo -e "\nERROR: You did not specify the installation mode!"
  echo "Please run the script in the terminal with one of the following parameters:\n"
  echo "  1. Local Installation:"
  echo "     ./install.sh local\n"
  echo "  2. Docker Installation:"
  echo "     ./install.sh docker\n"
  exit 1
fi

echo "Installation Mode: $MODE"
INSTALL_DIR="${ORION_INSTALL_DIR:-$HOME/.orion-router}"
REPO_URL="https://github.com/orion-ai-assistant/orion-router.git"
echo "Target Directory:  $INSTALL_DIR"

# 1. Requirement Checks
echo -e "\n[1/5] Checking system requirements..."
if [ "$MODE" = "local" ]; then
  REQUIRED_CMDS=(git python3 npm)
else
  REQUIRED_CMDS=(git docker)
fi

for cmd in "${REQUIRED_CMDS[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: '$cmd' not found! Please install it and try again." >&2
    exit 1
  fi
done
echo "✔ Requirements met (${REQUIRED_CMDS[*]})."

# macOS-specific PostgreSQL check and auto-install for local execution
if [ "$MODE" = "local" ] && [ "$(uname)" = "Darwin" ]; then
  echo "Checking PostgreSQL status on macOS..."
  # Check standard path and Homebrew paths
  if ! command -v pg_ctl >/dev/null 2>&1 && ! command -v initdb >/dev/null 2>&1; then
    echo "PostgreSQL not found. Attempting to install postgresql@16 via Homebrew..."
    if command -v brew >/dev/null 2>&1; then
      BREW_PREFIX=$(brew --prefix)
      USER_LOGS="$HOME/Library/Logs/Homebrew"
      
      # Ensure logs directory exists
      mkdir -p "$USER_LOGS" 2>/dev/null || true
      
      # Verify if directories are writable by current user
      if [ ! -w "$BREW_PREFIX" ] || [ ! -w "$USER_LOGS" ] || [ -d "$BREW_PREFIX/Cellar" -a ! -w "$BREW_PREFIX/Cellar" ]; then
        echo -e "\n[!] Homebrew directories are not writable by your user."
        echo "Requesting administrator privileges (sudo) to automatically fix Homebrew write permissions..."
        sudo chown -R "$(whoami)" "$USER_LOGS" "$BREW_PREFIX"
        chmod u+w "$USER_LOGS" "$BREW_PREFIX"
      fi

      # Attempt install
      brew install postgresql@16 || { echo "WARNING: Homebrew installation failed. Please install PostgreSQL manually."; }
      brew services start postgresql@16 || true
      brew link postgresql@16 --force || true
      export PATH="$BREW_PREFIX/opt/postgresql@16/bin:$PATH"
    else
      echo "Homebrew is not installed! Please install Homebrew or install PostgreSQL manually (e.g. Postgres.app)."
    fi
  else
    echo "✔ PostgreSQL binaries are available."
  fi
fi

# 2. Repo Clone or Update
echo -e "\n[2/5] Setting up Orion Router directory..."

STOP_SCRIPT="$INSTALL_DIR/bin/stop.py"
if [ -f "$STOP_SCRIPT" ]; then
  python3 "$STOP_SCRIPT" --quiet >/dev/null 2>&1 || true
fi

if [ -f "main.py" ] && [ -f "bin/common.py" ]; then
  echo "✔ Installing from local directory files..."
  if [ "$INSTALL_DIR" != "$(pwd)" ]; then
    mkdir -p "$INSTALL_DIR"
    # Copy all files except git folders, postgres data, tools, and node_modules
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --exclude='.git' --exclude='.pgdata*' --exclude='tools' --exclude='node_modules' ./ "$INSTALL_DIR/"
    else
      cp -R . "$INSTALL_DIR/"
      rm -rf "$INSTALL_DIR/.git" "$INSTALL_DIR/.pgdata*" "$INSTALL_DIR/tools" "$INSTALL_DIR/node_modules" "$INSTALL_DIR/dashboard/node_modules" 2>/dev/null || true
    fi
  fi
else
  if [ ! -d "$INSTALL_DIR" ]; then
    # Case 1: No folder at all — fresh clone
    echo "[OK] Cloning fresh copy from GitHub..."
    git clone "$REPO_URL" "$INSTALL_DIR"

  elif [ ! -d "$INSTALL_DIR/.git" ]; then
    # Case 2: Folder exists but no .git — init in-place (avoids rm -rf on locked dirs)
    echo "[!] Folder exists but has no git repository. Initializing in-place..."
    cd "$INSTALL_DIR"
    git init
    # Safely set remote (remove if exists, then add)
    git remote remove origin 2>/dev/null || true
    git remote add origin "$REPO_URL"
    git fetch origin main || { echo "[ERROR] git fetch failed. Check your internet connection."; exit 1; }
    git reset --hard origin/main || { echo "[ERROR] git reset failed."; exit 1; }
    echo "✔ Repository initialized and updated."

  else
    # Case 3: Folder + .git exist — ensure remote is correct URL then update
    echo "✔ Directory exists, forcing updates from GitHub..."
    cd "$INSTALL_DIR"
    # Fix remote URL in case it was broken by a previous failed install
    git remote set-url origin "$REPO_URL" 2>/dev/null || git remote add origin "$REPO_URL"
    git fetch origin main || { echo "[ERROR] git fetch failed. There might be a connection issue."; exit 1; }
    git reset --hard origin/main || { echo "[ERROR] Resetting/updating code failed."; exit 1; }
  fi
fi
cd "$INSTALL_DIR"


# --- Smart .env Check ---
echo -e "\n[*] Checking .env file..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✔ .env file not found. Created a new .env file from .env.example to prevent Docker warnings."
    else
        echo "[!] .env.example not found, creating an empty .env file..."
        touch .env
    fi
else
    echo "✔ Existing .env file detected. Kept intact to preserve your configurations."
fi

# 3 & 4. Dependencies
if [ "$MODE" = "local" ]; then
    echo -e "\n[3/5] Installing Python packages (pip)..."
    if python3 -m pip install --help 2>&1 | grep -q "break-system-packages"; then
      python3 -m pip install --break-system-packages -e . || echo "WARNING: pip install failed. Continuing..."
    else
      python3 -m pip install -e . || echo "WARNING: pip install failed. Continuing..."
    fi
    echo -e "\n[4/5] Installing Dashboard dependencies (NPM)..."
    if [ -d "dashboard" ]; then
        (cd dashboard && npm install || echo "WARNING: npm install failed. Continuing...")
    fi
else
    echo -e "\n[3/5] and [4/5] Steps Skipped..."
    echo "Docker mode selected; local dependencies will not be installed. Only GHCR images will be pulled."
fi

# 5. Global Command Installation
echo -e "\n[5/5] Installing global 'orionrouter' command..."

if [ "$(uname)" = "Darwin" ]; then
  if [ -f "$HOME/.zshrc" ]; then
    PROFILE="$HOME/.zshrc"
  elif [ -f "$HOME/.bash_profile" ]; then
    PROFILE="$HOME/.bash_profile"
  else
    PROFILE="$HOME/.profile"
  fi
elif [ -n "${ZSH_VERSION:-}" ]; then
  PROFILE="$HOME/.zshrc"
elif [ -n "${BASH_VERSION:-}" ]; then
  PROFILE="$HOME/.bashrc"
else
  PROFILE="$HOME/.profile"
fi

# Clean old entries
if [ -f "$PROFILE" ]; then
  sed -i.bak '/# --- ORION ROUTER CLI START ---/,/# --- ORION ROUTER CLI END ---/d' "$PROFILE" 2>/dev/null || true
  sed -i.bak '/^[[:space:]]*orion-router\([[:space:]]\+start\)\?[[:space:]]*$/d' "$PROFILE" 2>/dev/null || true
  sed -i.bak '/^[[:space:]]*orionrouter\([[:space:]]\+start\)\?[[:space:]]*$/d' "$PROFILE" 2>/dev/null || true
  rm -f "${PROFILE}.bak"
fi

# Create CLI script based on mode
CLI_SCRIPT="$INSTALL_DIR/orionrouter"

if [ "$MODE" = "local" ]; then
cat > "$CLI_SCRIPT" << 'EOF'
#!/usr/bin/env bash

ACTION="${1:-help}"
PROJECT_DIR="${ORION_INSTALL_DIR:-$HOME/.orion-router}"
PID_FILE="$PROJECT_DIR/.orion.pid"
LOG_FILE="$PROJECT_DIR/orion_output.log"
ERROR_LOG_FILE="$PROJECT_DIR/orion_error.log"

ORIGINAL_DIR=$(pwd)
trap 'cd "$ORIGINAL_DIR"' EXIT

if [ "$ACTION" = "help" ] || [ -z "$ACTION" ]; then
    echo ""
    echo "  Orion Router CLI"
    echo "  --------------------------------"
    echo "  Usage: orionrouter <command>"
    echo ""
    echo "  Commands:"
    echo "    start   Starts the server in the background"
    echo "    stop    Stops the running server and all child processes"
    echo "    logs    Shows background logs and errors"
    echo "    help    Shows this help menu"
    echo ""
elif [ "$ACTION" = "start" ]; then
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "[OK] Orion Router is already running in the background!"
            echo "To view logs: orionrouter logs"
            exit 0
        fi
        rm -f "$PID_FILE"
    fi

    echo "Starting Orion Router locally..."
    cd "$PROJECT_DIR"
    nohup python3 orion.py prod > "$LOG_FILE" 2> "$ERROR_LOG_FILE" &
    echo $! > "$PID_FILE"
    
    PORT="20128"
    if [ -f "$PROJECT_DIR/.env" ]; then
        ENV_PORT=$(grep -E "^ROUTER_PORT=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '\r\n ' || true)
        if [ -n "$ENV_PORT" ]; then
            PORT="$ENV_PORT"
        fi
    fi
    URL="http://127.0.0.1:$PORT"
    
    if command -v ipconfig >/dev/null 2>&1; then
        LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
    elif command -v hostname >/dev/null 2>&1; then
        LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    else
        LOCAL_IP="127.0.0.1"
    fi
    LOCAL_URL="http://${LOCAL_IP}:${PORT}"

    echo -e "\n\033[90m────────────────────────────────────────────────\033[0m"
    echo -e "\033[94m\033[1mORION ROUTER\033[0m\n"
    echo -e "\033[94m➜\033[0m  \033[1mDashboard:\033[0m   \033[96m\033[4m${URL}\033[0m"
    echo -e "\033[94m➜\033[0m  \033[1mYerel Ağ:\033[0m    \033[96m\033[4m${LOCAL_URL}\033[0m"
    echo -e "\033[90m────────────────────────────────────────────────\033[0m"
    echo -e "\033[90mKomutlar: orionrouter start | stop | logs | help\033[0m\n"

    echo "Streaming live logs... (Press Ctrl+C to exit)"
    tail -f "$LOG_FILE"
elif [ "$ACTION" = "stop" ]; then
    STOP_SCRIPT="$PROJECT_DIR/bin/stop.py"
    if [ -f "$STOP_SCRIPT" ]; then
        python3 "$STOP_SCRIPT" || true
    fi
    echo "[OK] Orion Router stopped."
elif [ "$ACTION" = "logs" ]; then
    PORT="20128"
    if [ -f "$PROJECT_DIR/.env" ]; then
        ENV_PORT=$(grep -E "^ROUTER_PORT=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '\r\n ' || true)
        if [ -n "$ENV_PORT" ]; then
            PORT="$ENV_PORT"
        fi
    fi
    URL="http://127.0.0.1:$PORT"

    if command -v ipconfig >/dev/null 2>&1; then
        LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
    elif command -v hostname >/dev/null 2>&1; then
        LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    else
        LOCAL_IP="127.0.0.1"
    fi
    LOCAL_URL="http://${LOCAL_IP}:${PORT}"

    echo -e "\n\033[90m────────────────────────────────────────────────\033[0m"
    echo -e "\033[94m\033[1mORION ROUTER\033[0m\n"
    echo -e "\033[94m➜\033[0m  \033[1mDashboard:\033[0m   \033[96m\033[4m${URL}\033[0m"
    echo -e "\033[94m➜\033[0m  \033[1mYerel Ağ:\033[0m    \033[96m\033[4m${LOCAL_URL}\033[0m"
    echo -e "\033[90m────────────────────────────────────────────────\033[0m"
    echo -e "\033[90mKomutlar: orionrouter start | stop | logs | help\033[0m\n"

    if [ -f "$ERROR_LOG_FILE" ]; then
        echo -e "\n[!] RECENT ERRORS (orion_error.log):"
        tail -15 "$ERROR_LOG_FILE"
        echo "----------------------------------------------------"
    fi
    if [ -f "$LOG_FILE" ]; then
        echo "  Streaming live logs... (Press Ctrl+C to exit)"
        tail -f "$LOG_FILE"
    else
        echo "No log file exists yet."
    fi
else
    echo "Invalid command. Type 'orionrouter help' for assistance."
fi
EOF
else
cat > "$CLI_SCRIPT" << 'EOF'
#!/usr/bin/env bash

ACTION="${1:-help}"
PROJECT_DIR="${ORION_INSTALL_DIR:-$HOME/.orion-router}"
COMPOSE_FILE="docker-compose.ghcr.yml"

ORIGINAL_DIR=$(pwd)
trap 'cd "$ORIGINAL_DIR"' EXIT

if [ "$ACTION" = "help" ] || [ -z "$ACTION" ]; then
    echo ""
    echo "  Orion Router CLI (Docker Mode)"
    echo "  --------------------------------"
    echo "  Usage: orionrouter <command>"
    echo ""
    echo "  Commands:"
    echo "    start   Starts container in the background"
    echo "    stop    Stops the running container"
    echo "    logs    Shows live container logs"
    echo "    help    Shows this help menu"
    echo ""
elif [ "$ACTION" = "start" ]; then
    echo "Checking Docker status..."
    DOCKER_READY=0
    if docker info >/dev/null 2>&1; then
        DOCKER_READY=1
    else
        echo "[!] Docker Daemon is not active. Attempting to start..."
        if command -v systemctl >/dev/null 2>&1; then
            sudo systemctl start docker || true
        elif [ "$(uname)" = "Darwin" ]; then
            open -a Docker || true
        fi

        echo "[*] Waiting for Docker Engine to be ready (max 30 seconds)..."
        for i in {1..6}; do
            sleep 5
            if docker info >/dev/null 2>&1; then
                DOCKER_READY=1
                echo "[OK] Docker Engine is active and ready!"
                break
            fi
            echo "    Initializing... ($((i * 5)) seconds elapsed)"
        done
    fi

    if [ $DOCKER_READY -eq 0 ]; then
        echo -e "\n[ERROR] Docker could not be started automatically, or the engine failed to respond in time."
        echo "Please open Docker Desktop and try again.\n"
        exit 1
    fi

    echo "Starting Orion Router on Docker (with GHCR Images)..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" -p orion-router up -d

    PORT="20128"
    if [ -f "$PROJECT_DIR/.env" ]; then
        ENV_PORT=$(grep -E "^ROUTER_PORT=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '\r\n ' || true)
        if [ -n "$ENV_PORT" ]; then
            PORT="$ENV_PORT"
        fi
    fi
    URL="http://127.0.0.1:$PORT"
    
    if command -v ipconfig >/dev/null 2>&1; then
        LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
    elif command -v hostname >/dev/null 2>&1; then
        LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    else
        LOCAL_IP="127.0.0.1"
    fi
    LOCAL_URL="http://${LOCAL_IP}:${PORT}"

    echo -e "\n\033[90m────────────────────────────────────────────────\033[0m"
    echo -e "\033[94m\033[1mORION ROUTER\033[0m\n"
    echo -e "\033[94m➜\033[0m  \033[1mDashboard:\033[0m   \033[96m\033[4m${URL}\033[0m"
    echo -e "\033[94m➜\033[0m  \033[1mYerel Ağ:\033[0m    \033[96m\033[4m${LOCAL_URL}\033[0m"
    echo -e "\033[90m────────────────────────────────────────────────\033[0m"
    echo -e "\033[90mKomutlar: orionrouter start | stop | logs | help\033[0m\n"

    echo "Streaming live logs... (Press Ctrl+C to exit)"
    docker compose -f "$COMPOSE_FILE" -p orion-router logs -f
elif [ "$ACTION" = "stop" ]; then
    echo "Stopping Orion Router on Docker..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" -p orion-router stop
    echo "[OK] Container stopped successfully."
elif [ "$ACTION" = "logs" ]; then
    PORT="20128"
    if [ -f "$PROJECT_DIR/.env" ]; then
        ENV_PORT=$(grep -E "^ROUTER_PORT=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '\r\n ' || true)
        if [ -n "$ENV_PORT" ]; then
            PORT="$ENV_PORT"
        fi
    fi
    URL="http://127.0.0.1:$PORT"

    if command -v ipconfig >/dev/null 2>&1; then
        LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
    elif command -v hostname >/dev/null 2>&1; then
        LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    else
        LOCAL_IP="127.0.0.1"
    fi
    LOCAL_URL="http://${LOCAL_IP}:${PORT}"

    echo -e "\n\033[90m────────────────────────────────────────────────\033[0m"
    echo -e "\033[94m\033[1mORION ROUTER\033[0m\n"
    echo -e "\033[94m➜\033[0m  \033[1mDashboard:\033[0m   \033[96m\033[4m${URL}\033[0m"
    echo -e "\033[94m➜\033[0m  \033[1mYerel Ağ:\033[0m    \033[96m\033[4m${LOCAL_URL}\033[0m"
    echo -e "\033[90m────────────────────────────────────────────────\033[0m"
    echo -e "\033[90mKomutlar: orionrouter start | stop | logs | help\033[0m\n"

    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" -p orion-router logs -f
else
    echo "Invalid command. Type 'orionrouter help' for assistance."
fi
EOF
fi

chmod +x "$CLI_SCRIPT"

# Add PATH to profile
if [ -f "$PROFILE" ]; then
    if ! grep -q "export PATH=\"$INSTALL_DIR:\$PATH\"" "$PROFILE" 2>/dev/null; then
        echo -e "\n# --- ORION ROUTER CLI START ---" >> "$PROFILE"
        echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$PROFILE"
        echo "# --- ORION ROUTER CLI END ---" >> "$PROFILE"
    fi
fi

# Try to symlink globally to /usr/local/bin or /opt/homebrew/bin so it works in the current active shell
echo "Registering 'orionrouter' command globally..."
if [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
    ln -sf "$CLI_SCRIPT" /usr/local/bin/orionrouter 2>/dev/null || true
    echo "✔ Global symlink created in /usr/local/bin"
elif [ -d "/opt/homebrew/bin" ] && [ -w "/opt/homebrew/bin" ]; then
    ln -sf "$CLI_SCRIPT" /opt/homebrew/bin/orionrouter 2>/dev/null || true
    echo "✔ Global symlink created in /opt/homebrew/bin"
else
    # Fallback to sudo if neither is writable (prompting user once)
    if [ -d "/usr/local/bin" ]; then
        echo "[!] Requesting administrator privileges (sudo) to register 'orionrouter' globally..."
        sudo ln -sf "$CLI_SCRIPT" /usr/local/bin/orionrouter 2>/dev/null || true
        echo "✔ Global symlink created in /usr/local/bin using sudo"
    fi
fi

# Apply to current session
export PATH="$INSTALL_DIR:$PATH"

if [ "$MODE" = "local" ]; then
    echo -e "\n[*] Pre-fetching resources (PostgreSQL) to display live progress..."
    python3 -c "import sys; sys.path.insert(0, '.'); from bin.prod import download_postgres; download_postgres(); from bin.npm_integrity import record_npm_install; from pathlib import Path; record_npm_install(Path('dashboard'))"
fi

echo ""
echo "[OK] Installation complete."
echo "[OK] 'orionrouter' command is globally registered and ready to use in this terminal and new ones!"
echo "[OK] Starting Orion Router..."

orionrouter start
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
INSTALL_DIR="$HOME/.orion-router"
REPO_URL="https://github.com/krstalacam/orion-router.git"
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

# 2. Repo Clone or Update
echo -e "\n[2/5] Setting up Orion Router directory..."

    STOP_SCRIPT="$INSTALL_DIR/bin/stop.py"
    if [ -f "$STOP_SCRIPT" ]; then
        python3 "$STOP_SCRIPT" --quiet >/dev/null 2>&1 || true
    fi

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
    python3 -m pip install -e .
    echo -e "\n[4/5] Installing Dashboard dependencies (NPM)..."
    if [ -d "dashboard" ]; then
        (cd dashboard && npm install)
    fi
else
    echo -e "\n[3/5] and [4/5] Steps Skipped..."
    echo "Docker mode selected; local dependencies will not be installed. Only GHCR images will be pulled."
fi

# 5. Global Command Installation
echo -e "\n[5/5] Installing global 'orionrouter' command..."

if [ -n "${ZSH_VERSION:-}" ]; then
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
PROJECT_DIR="$HOME/.orion-router"
PID_FILE="$PROJECT_DIR/.orion.pid"
LOG_FILE="$PROJECT_DIR/orion_output.log"
ERROR_LOG_FILE="$PROJECT_DIR/orion_error.log"

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
    
    echo "[OK] Orion Router started running in the background!"
    echo "[OK] You can now use these commands: orionrouter start | stop | logs | help"
    echo "----------------------------------------------------"
    echo "  Streaming live logs... (Press Ctrl+C to exit)"
    echo "----------------------------------------------------"
    tail -f "$LOG_FILE"
elif [ "$ACTION" = "stop" ]; then
    STOP_SCRIPT="$PROJECT_DIR/bin/stop.py"
    if [ -f "$STOP_SCRIPT" ]; then
        python3 "$STOP_SCRIPT" || true
    fi
    echo "[OK] Orion Router stopped."
elif [ "$ACTION" = "logs" ]; then
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
PROJECT_DIR="$HOME/.orion-router"
COMPOSE_FILE="docker-compose.ghcr.yml"

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
    echo "[OK] Container started! To stop, type 'orionrouter stop'."
    echo "[OK] You can now use these commands: orionrouter start | stop | logs | help"
    echo "----------------------------------------------------"
    echo "  Streaming live logs... (Press Ctrl+C to exit)"
    echo "----------------------------------------------------"
    docker compose -f "$COMPOSE_FILE" -p orion-router logs -f
elif [ "$ACTION" = "stop" ]; then
    echo "Stopping Orion Router on Docker..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" -p orion-router stop
    echo "[OK] Container stopped successfully."
elif [ "$ACTION" = "logs" ]; then
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

# Apply to current session
export PATH="$INSTALL_DIR:$PATH"

echo ""
echo "[OK] Installation complete."
echo "[OK] 'orionrouter' command is ready in this terminal and new ones."
echo "     Available commands: orionrouter start | stop | logs | help"
echo "     You can close this terminal after starting."
echo "[OK] Starting Orion Router..."

orionrouter start
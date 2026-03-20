#!/usr/bin/env bash
#
# Claude Note Installer
#
# Installs claude-note using uv for session logging with Claude Code.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/artemiin/claude-note/main/install.sh | bash
#   # or
#   ./install.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Installation paths
CONFIG_DIR="${HOME}/.config/claude-note"
REPO_URL="https://github.com/artemiin/claude-note.git"

# Detect OS (including Git Bash / MSYS2 on Windows)
OS="$(uname -s)"
case "${OS}" in
    Linux*)                     OS_TYPE=linux;;
    Darwin*)                    OS_TYPE=macos;;
    MINGW*|MSYS*|CYGWIN*)       OS_TYPE=windows;;
    *)                          OS_TYPE=unknown;;
esac

# ASCII Art Banner
echo
echo -e "${RED}  ██████╗██╗      █████╗ ██╗   ██╗██████╗ ███████╗${NC}"
echo -e "${RED} ██╔════╝██║     ██╔══██╗██║   ██║██╔══██╗██╔════╝${NC}"
echo -e "${RED} ██║     ██║     ███████║██║   ██║██║  ██║█████╗  ${NC}"
echo -e "${RED} ██║     ██║     ██╔══██║██║   ██║██║  ██║██╔══╝  ${NC}"
echo -e "${RED} ╚██████╗███████╗██║  ██║╚██████╔╝██████╔╝███████╗${NC}"
echo -e "${RED}  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝${NC}"
echo -e "${GREEN} ███╗   ██╗ ██████╗ ████████╗███████╗${NC}"
echo -e "${GREEN} ████╗  ██║██╔═══██╗╚══██╔══╝██╔════╝${NC}"
echo -e "${GREEN} ██╔██╗ ██║██║   ██║   ██║   █████╗  ${NC}"
echo -e "${GREEN} ██║╚██╗██║██║   ██║   ██║   ██╔══╝  ${NC}"
echo -e "${GREEN} ██║ ╚████║╚██████╔╝   ██║   ███████╗${NC}"
echo -e "${GREEN} ╚═╝  ╚═══╝ ╚═════╝    ╚═╝   ╚══════╝${NC}"
echo
echo -e "  ${BLUE}>${NC} ${GREEN}\$ ./install.sh${NC} ... ${GREEN}OK${NC}"
echo

# =============================================================================
# Preflight Checks
# =============================================================================

echo -e "${BLUE}[1/8]${NC} Checking requirements..."

# Check for uv
if command -v uv &>/dev/null; then
    UV_VERSION=$(uv --version 2>/dev/null | head -1)
    echo -e "  ${GREEN}✓${NC} uv found ($UV_VERSION)"
else
    echo -e "  ${YELLOW}!${NC} uv not found"
    echo "    uv is required for installation."
    echo
    read -p "    Install uv now? [Y/n] " INSTALL_UV
    if [[ -z "$INSTALL_UV" || "$INSTALL_UV" =~ ^[Yy] ]]; then
        echo "    Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # Source the updated PATH
        export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:$PATH"
        if command -v uv &>/dev/null; then
            echo -e "  ${GREEN}✓${NC} uv installed successfully"
        else
            echo -e "${RED}Error: uv installation failed${NC}"
            echo "Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
            exit 1
        fi
    else
        echo "Please install uv first: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi

# Check git
if ! command -v git &>/dev/null; then
    echo -e "${RED}Error: git is required${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} git found"

# Check Claude CLI (warn but continue)
if command -v claude &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Claude CLI found"
    CLAUDE_AVAILABLE=true
else
    echo -e "  ${YELLOW}!${NC} Claude CLI not found (synthesis will be disabled)"
    echo "    Install from: https://claude.ai/download"
    CLAUDE_AVAILABLE=false
fi

# Check qmd (optional but recommended)
if command -v qmd &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} qmd found (semantic search enabled)"
    QMD_AVAILABLE=true
else
    echo -e "  ${YELLOW}!${NC} qmd not found (semantic search disabled)"
    echo "    Synthesis will work but without vault context."
    echo "    Install qmd for better results: https://github.com/tobi/qmd"
    echo
    read -p "    Continue without qmd? [Y/n] " CONTINUE_NO_QMD
    if [[ "$CONTINUE_NO_QMD" =~ ^[Nn] ]]; then
        echo "Install qmd first, then re-run this installer."
        exit 0
    fi
    QMD_AVAILABLE=false
fi

# =============================================================================
# Get Vault Path
# =============================================================================

echo
echo -e "${BLUE}[2/8]${NC} Configuring vault..."

# Check for existing config
if [[ -f "${CONFIG_DIR}/config.toml" ]]; then
    EXISTING_VAULT=$(grep -E '^vault_root\s*=' "${CONFIG_DIR}/config.toml" 2>/dev/null | sed -E 's/.*=[[:space:]]*"?([^"]*)"?/\1/' || true)
    if [[ -n "$EXISTING_VAULT" ]]; then
        echo -e "  Found existing config: ${EXISTING_VAULT}"
        read -p "  Use this vault? [Y/n] " USE_EXISTING
        if [[ -z "$USE_EXISTING" || "$USE_EXISTING" =~ ^[Yy] ]]; then
            VAULT_PATH="$EXISTING_VAULT"
        fi
    fi
fi

# Prompt for vault path if not set
if [[ -z "$VAULT_PATH" ]]; then
    DEFAULT_VAULT="${HOME}/Documents/claude-notes"
    echo "  Enter the path to your Obsidian vault or notes directory."
    echo "  Press Enter to create a new folder at: ${DEFAULT_VAULT}"
    echo
    read -p "  Vault path [${DEFAULT_VAULT}]: " VAULT_PATH

    # Use default if empty
    if [[ -z "$VAULT_PATH" ]]; then
        VAULT_PATH="$DEFAULT_VAULT"
    fi

    # Expand ~ to home directory
    VAULT_PATH="${VAULT_PATH/#\~/$HOME}"

    if [[ ! -d "$VAULT_PATH" ]]; then
        read -p "  Directory doesn't exist. Create it? [Y/n] " CREATE_DIR
        if [[ -z "$CREATE_DIR" || "$CREATE_DIR" =~ ^[Yy] ]]; then
            mkdir -p "$VAULT_PATH"
            echo -e "  ${GREEN}✓${NC} Created $VAULT_PATH"
        else
            echo -e "${RED}Error: Vault directory required${NC}"
            exit 1
        fi
    fi
fi

echo -e "  ${GREEN}✓${NC} Vault: $VAULT_PATH"

# =============================================================================
# Install with uv
# =============================================================================

echo
echo -e "${BLUE}[3/8]${NC} Installing claude-note with uv..."

# Ensure Python 3.11+ is available via uv
echo "  Ensuring Python 3.11 is available..."
uv python install 3.11 --quiet 2>/dev/null || true

# Check if we're running from the repo itself
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/pyproject.toml" ]]; then
    # Install from local directory
    echo "  Installing from local directory..."
    uv tool install "${SCRIPT_DIR}" --python 3.11 --force --quiet
else
    # Clone and install from repo
    echo "  Cloning repository..."
    TEMP_DIR=$(mktemp -d)
    trap "rm -rf ${TEMP_DIR}" EXIT
    git clone --quiet --depth 1 "$REPO_URL" "${TEMP_DIR}/claude-note"

    echo "  Installing..."
    uv tool install "${TEMP_DIR}/claude-note" --python 3.11 --force --quiet
fi

# Verify installation
if command -v claude-note &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} claude-note installed successfully"
else
    # uv tool bin directory might not be in PATH yet
    UV_TOOL_BIN="${HOME}/.local/bin"
    if [[ -f "${UV_TOOL_BIN}/claude-note" ]]; then
        echo -e "  ${GREEN}✓${NC} claude-note installed to ${UV_TOOL_BIN}"
        echo -e "  ${YELLOW}!${NC} Add ${UV_TOOL_BIN} to your PATH:"
        echo "    export PATH=\"\$PATH:${UV_TOOL_BIN}\""
    else
        echo -e "${RED}Error: Installation failed${NC}"
        exit 1
    fi
fi

# Get the actual binary path for service configuration
CLAUDE_NOTE_BIN=$(command -v claude-note 2>/dev/null || echo "${HOME}/.local/bin/claude-note")

# =============================================================================
# Copy vault templates (if installing from local repo)
# =============================================================================

echo
echo -e "${BLUE}[4/8]${NC} Setting up vault templates..."

TEMPLATE_DIR="${SCRIPT_DIR}/vault-template"
if [[ -d "$TEMPLATE_DIR" ]]; then
    read -p "  Copy starter templates to vault? [Y/n] " COPY_TEMPLATES
    if [[ -z "$COPY_TEMPLATES" || "$COPY_TEMPLATES" =~ ^[Yy] ]]; then
        # Copy CLAUDE.md if it doesn't exist
        if [[ ! -f "${VAULT_PATH}/CLAUDE.md" ]]; then
            cp "${TEMPLATE_DIR}/CLAUDE.md" "${VAULT_PATH}/"
            echo -e "  ${GREEN}✓${NC} Created CLAUDE.md"
        fi

        # Copy inbox if it doesn't exist
        if [[ ! -f "${VAULT_PATH}/claude-note-inbox.md" ]]; then
            cp "${TEMPLATE_DIR}/claude-note-inbox.md" "${VAULT_PATH}/"
            echo -e "  ${GREEN}✓${NC} Created claude-note-inbox.md"
        fi

        # Copy open-questions.md if it doesn't exist
        if [[ ! -f "${VAULT_PATH}/open-questions.md" ]]; then
            cp "${TEMPLATE_DIR}/open-questions.md" "${VAULT_PATH}/"
            echo -e "  ${GREEN}✓${NC} Created open-questions.md"
        fi

        # Copy templates directory
        if [[ ! -d "${VAULT_PATH}/templates" ]]; then
            cp -r "${TEMPLATE_DIR}/templates" "${VAULT_PATH}/"
            echo -e "  ${GREEN}✓${NC} Created templates/"
        fi
    else
        echo "  Skipping templates"
    fi
else
    echo "  (no local templates available)"
fi

# =============================================================================
# Write Configuration
# =============================================================================

echo
echo -e "${BLUE}[5/8]${NC} Writing configuration..."

mkdir -p "$CONFIG_DIR"

# Determine synthesis mode
if [[ "$CLAUDE_AVAILABLE" == true ]]; then
    SYNTH_MODE="route"
else
    SYNTH_MODE="log"
fi

cat > "${CONFIG_DIR}/config.toml" << EOF
# Claude Note Configuration
# See docs/configuration.md for all options

vault_root = "${VAULT_PATH}"

# Synthesis mode: log | inbox | route
# - log: Session logging only, no synthesis
# - inbox: Synthesize and append to inbox
# - route: Full synthesis with note creation/updates
[synthesis]
mode = "${SYNTH_MODE}"
model = "claude-sonnet-4-5-20250929"

# QMD semantic search (optional, requires qmd tool)
[qmd]
enabled = ${QMD_AVAILABLE}
synth_max_notes = 5
EOF

echo -e "  ${GREEN}✓${NC} Config at ${CONFIG_DIR}/config.toml"

# =============================================================================
# Initialize Vault Structure
# =============================================================================

echo
echo -e "${BLUE}[6/8]${NC} Initializing vault structure..."

# Create .claude-note directories
mkdir -p "${VAULT_PATH}/.claude-note/queue"
mkdir -p "${VAULT_PATH}/.claude-note/state"
mkdir -p "${VAULT_PATH}/.claude-note/logs"

echo -e "  ${GREEN}✓${NC} Created .claude-note/ directories"

# v2: Company vault structure
echo
read -p "  Setup multi-agent company vault? [y/N] " SETUP_COMPANY
if [[ "$SETUP_COMPANY" =~ ^[Yy] ]]; then
    for dir in _hub _agents executive marketing sales engineering product operations journal literature; do
        mkdir -p "${VAULT_PATH}/${dir}"
    done
    # Create department subdirs
    mkdir -p "${VAULT_PATH}/executive/"{board-updates,fundraising,leadership}
    mkdir -p "${VAULT_PATH}/marketing/"{campaigns,brand,content-strategy,analytics}
    mkdir -p "${VAULT_PATH}/sales/"{pipeline,accounts,playbooks,pricing}
    mkdir -p "${VAULT_PATH}/engineering/"{architecture,infrastructure,incidents,tech-decisions}
    mkdir -p "${VAULT_PATH}/product/"{roadmap,features,user-research}
    mkdir -p "${VAULT_PATH}/operations/"{processes,playbooks,templates}
    mkdir -p "${VAULT_PATH}/.claude-note/graph"
    mkdir -p "${VAULT_PATH}/.claude-note/agents"

    echo -e "  ${GREEN}✓${NC} Created v2 department structure"
    echo "  Run 'claude-note agents init' to create agent profiles"
fi

# =============================================================================
# Setup Service
# =============================================================================

echo
echo -e "${BLUE}[7/8]${NC} Setting up background worker..."

if [[ "$OS_TYPE" == "macos" ]]; then
    # macOS launchd setup
    PLIST_NAME="com.claude-note.worker"
    PLIST_PATH="${HOME}/Library/LaunchAgents/${PLIST_NAME}.plist"

    mkdir -p "${HOME}/Library/LaunchAgents"

    cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${CLAUDE_NOTE_BIN}</string>
        <string>worker</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${VAULT_PATH}/.claude-note/logs/worker-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${VAULT_PATH}/.claude-note/logs/worker-stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${HOME}/.local/bin:${HOME}/.bun/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

    # Load the service
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"

    echo -e "  ${GREEN}✓${NC} Service installed and started"
    echo "  Commands:"
    echo "    launchctl stop ${PLIST_NAME}   # Stop worker"
    echo "    launchctl start ${PLIST_NAME}  # Start worker"

elif [[ "$OS_TYPE" == "linux" ]]; then
    # Linux systemd setup
    SERVICE_PATH="${HOME}/.config/systemd/user/claude-note.service"

    mkdir -p "${HOME}/.config/systemd/user"

    cat > "$SERVICE_PATH" << EOF
[Unit]
Description=Claude Note Background Worker
After=network.target

[Service]
Type=simple
ExecStart=${CLAUDE_NOTE_BIN} worker
Restart=always
RestartSec=5
Environment=PATH=${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
EOF

    # Reload and start the service
    systemctl --user daemon-reload
    systemctl --user enable claude-note.service
    systemctl --user start claude-note.service

    echo -e "  ${GREEN}✓${NC} Service installed and started"
    echo "  Commands:"
    echo "    systemctl --user stop claude-note    # Stop worker"
    echo "    systemctl --user start claude-note   # Start worker"
    echo "    systemctl --user status claude-note  # Check status"
elif [[ "$OS_TYPE" == "windows" ]]; then
    # Windows Task Scheduler setup
    TASK_NAME="ClaudeNoteWorker"
    WINDOWS_BIN=$(cygpath -w "$CLAUDE_NOTE_BIN" 2>/dev/null || echo "$CLAUDE_NOTE_BIN")

    schtasks.exe /Create /TN "$TASK_NAME" /TR "\"$WINDOWS_BIN\" worker" \
        /SC ONLOGON /RL HIGHEST /F 2>/dev/null

    if [[ $? -eq 0 ]]; then
        schtasks.exe /Run /TN "$TASK_NAME" 2>/dev/null
        echo -e "  ${GREEN}✓${NC} Task Scheduler entry created and started"
        echo "  Commands:"
        echo "    schtasks.exe /End /TN $TASK_NAME    # Stop worker"
        echo "    schtasks.exe /Run /TN $TASK_NAME    # Start worker"
        echo "    schtasks.exe /Delete /TN $TASK_NAME # Remove"
    else
        echo -e "  ${YELLOW}!${NC} Could not create Task Scheduler entry"
        echo "  Run manually: claude-note worker"
    fi
else
    echo -e "  ${YELLOW}!${NC} Unknown OS - skipping service setup"
    echo "  Run manually: claude-note worker"
fi

# ============================================================================
# Setup Classifier Timer (v2)
# ============================================================================

echo
echo -e "${BLUE}[7.5/8]${NC} Setting up classifier timer (v2)..."

read -p "  Setup classifier job (processes agent inboxes every 15 min)? [y/N] " SETUP_CLASSIFIER
if [[ "$SETUP_CLASSIFIER" =~ ^[Yy] ]]; then
    if [[ "$OS_TYPE" == "linux" ]]; then
        # systemd timer
        cat > "${HOME}/.config/systemd/user/claude-note-classifier.service" << EOF
[Unit]
Description=Claude Note Classifier Job

[Service]
Type=oneshot
ExecStart=${CLAUDE_NOTE_BIN} classify
EOF
        cat > "${HOME}/.config/systemd/user/claude-note-classifier.timer" << EOF
[Unit]
Description=Run Claude Note Classifier every 15 min

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
EOF
        systemctl --user daemon-reload
        systemctl --user enable --now claude-note-classifier.timer
        echo -e "  ${GREEN}✓${NC} Classifier timer installed (systemd)"

    elif [[ "$OS_TYPE" == "macos" ]]; then
        CLASSIFIER_PLIST="${HOME}/Library/LaunchAgents/com.claude-note.classifier.plist"
        cat > "$CLASSIFIER_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-note.classifier</string>
    <key>ProgramArguments</key>
    <array>
        <string>${CLAUDE_NOTE_BIN}</string>
        <string>classify</string>
    </array>
    <key>StartInterval</key>
    <integer>900</integer>
    <key>StandardOutPath</key>
    <string>${VAULT_PATH}/.claude-note/logs/classifier-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${VAULT_PATH}/.claude-note/logs/classifier-stderr.log</string>
</dict>
</plist>
EOF
        launchctl load "$CLASSIFIER_PLIST" 2>/dev/null
        echo -e "  ${GREEN}✓${NC} Classifier timer installed (launchd, every 15 min)"

    elif [[ "$OS_TYPE" == "windows" ]]; then
        schtasks.exe /Create /TN "ClaudeNoteClassifier" \
            /TR "\"$WINDOWS_BIN\" classify" \
            /SC MINUTE /MO 15 /F 2>/dev/null
        echo -e "  ${GREEN}✓${NC} Classifier timer installed (Task Scheduler, every 15 min)"
    fi
else
    echo "  Skipping classifier timer"
fi

# =============================================================================
# GitNexus Code Intelligence (v2 - optional)
# =============================================================================

echo
echo -e "${BLUE}[8/9]${NC} GitNexus code intelligence (optional)..."

read -p "  Setup GitNexus code intelligence? [y/N] " SETUP_GITNEXUS
if [[ "$SETUP_GITNEXUS" =~ ^[Yy] ]]; then
    if command -v npx &>/dev/null; then
        echo "  Indexing current repository with GitNexus..."
        npx -y gitnexus@latest analyze --skills 2>/dev/null
        if [[ $? -eq 0 ]]; then
            echo -e "  ${GREEN}✓${NC} Repository indexed with GitNexus"
            echo "  Generated skill files in .claude/skills/generated/"
        else
            echo -e "  ${YELLOW}!${NC} GitNexus indexing failed (is this a git repo?)"
        fi
    else
        echo -e "  ${YELLOW}!${NC} npx not found. Install Node.js for GitNexus: https://nodejs.org/"
    fi
else
    echo "  Skipping GitNexus setup"
    echo "  To set up later: npx gitnexus analyze --skills"
fi

# =============================================================================
# Install Claude Code Hooks
# =============================================================================

echo
echo -e "${BLUE}[9/10]${NC} Installing Claude Code hooks..."

CLAUDE_SETTINGS="${HOME}/.claude/settings.json"
mkdir -p "${HOME}/.claude"

# Use Python to merge hooks into settings.json (jq may not be installed)
python3 -c "
import json, sys
from pathlib import Path

settings_path = Path('${CLAUDE_SETTINGS}')
if settings_path.exists():
    settings = json.loads(settings_path.read_text())
else:
    settings = {}

hooks = settings.get('hooks', {})
enqueue_cmd = {'type': 'command', 'command': 'claude-note enqueue', 'timeout': 5000}
context_cmd = {'type': 'command', 'command': 'claude-note context', 'timeout': 5000}

hooks['SessionStart'] = [{'hooks': [context_cmd]}]
hooks['PostToolUse'] = [{'hooks': [enqueue_cmd]}]
hooks['UserPromptSubmit'] = [{'hooks': [enqueue_cmd]}]
hooks['PostCompact'] = [{'hooks': [context_cmd]}]
hooks['Stop'] = [{'hooks': [enqueue_cmd]}]
settings['hooks'] = hooks

settings_path.write_text(json.dumps(settings, indent=2))
print('ok')
" 2>/dev/null

if [[ $? -eq 0 ]]; then
    echo -e "  ${GREEN}✓${NC} Hooks installed in ${CLAUDE_SETTINGS}"
else
    echo -e "  ${YELLOW}!${NC} Could not auto-install hooks. Add manually to ${CLAUDE_SETTINGS}:"
    echo '     "hooks": {'
    echo '       "PostToolUse": [{ "hooks": [{ "type": "command", "command": "claude-note enqueue", "timeout": 5000 }] }],'
    echo '       "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "claude-note enqueue", "timeout": 5000 }] }],'
    echo '       "Stop": [{ "hooks": [{ "type": "command", "command": "claude-note enqueue", "timeout": 5000 }] }]'
    echo '     }'
fi

# =============================================================================
# Install Claude Code Skills
# =============================================================================

echo
echo -e "${BLUE}[10/10]${NC} Installing Claude Code skills..."

SKILLS_DIR="${HOME}/.claude/skills"
mkdir -p "${SKILLS_DIR}"

# Copy ingest skill if available
if [[ -d "${SCRIPT_DIR}/skills/ingest" ]]; then
    cp -r "${SCRIPT_DIR}/skills/ingest" "${SKILLS_DIR}/"
    echo -e "  ${GREEN}✓${NC} Installed /ingest skill"
else
    echo "  (no local skills available)"
fi

# =============================================================================
# Final Instructions
# =============================================================================

echo
echo -e "${GREEN}"
cat << 'BANNER'
  ╔═══════════════════════════════════════════╗
  ║  ✓ INSTALLATION COMPLETE                  ║
  ║    claude-note is ready to capture        ║
  ║    knowledge from your sessions  ✎        ║
  ╚═══════════════════════════════════════════╝
BANNER
echo -e "${NC}"
echo -e "${BLUE}> Next steps:${NC}"
echo
echo "1. Check status:"
echo "   claude-note status"
echo
echo "2. View logs:"
echo "   tail -f ${VAULT_PATH}/.claude-note/logs/worker-*.log"
echo
echo "3. For multi-agent setup:"
echo "   claude-note agents init"
echo

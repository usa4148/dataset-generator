#!/usr/bin/env bash
# install.sh — Dataset Generator installer
# Supports macOS, Linux, and Windows (Git Bash / WSL)
set -euo pipefail

# ── Colours (suppressed if not a terminal) ─────────────────────────────────────
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BOLD=''; RESET=''
fi

info()    { echo -e "${BOLD}$*${RESET}"; }
success() { echo -e "${GREEN}✓ $*${RESET}"; }
warn()    { echo -e "${YELLOW}⚠  $*${RESET}"; }
error()   { echo -e "${RED}✗  $*${RESET}" >&2; exit 1; }

# ── Detect OS ──────────────────────────────────────────────────────────────────
OS="$(uname -s 2>/dev/null || echo 'Unknown')"
case "$OS" in
    Darwin)            OS_NAME="macOS" ;;
    Linux)             OS_NAME="Linux" ;;
    MINGW*|MSYS*|CYGWIN*) OS_NAME="Windows (Git Bash)" ;;
    *)                 OS_NAME="$OS" ;;
esac

echo ""
info "Dataset Generator — Installer"
info "============================="
echo "  Platform : $OS_NAME"
echo ""

# ── Find Python 3.9+ ───────────────────────────────────────────────────────────
PYTHON=""
for candidate in python3 python python3.13 python3.12 python3.11 python3.10 python3.9; do
    if command -v "$candidate" &>/dev/null; then
        _ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        _major=$(echo "$_ver" | cut -d. -f1)
        _minor=$(echo "$_ver" | cut -d. -f2)
        if [ "$_major" -ge 3 ] && [ "$_minor" -ge 9 ]; then
            PYTHON="$candidate"
            PY_VERSION="$_ver"
            break
        fi
    fi
done

[ -z "$PYTHON" ] && error "Python 3.9+ not found. Install it from https://python.org and re-run."
success "Python $PY_VERSION  ($PYTHON)"

# ── Choose a safe venv location ────────────────────────────────────────────────
# Python venv fails if the project path contains ':' (Unix PATH separator).
# Fall back to a home-directory location if that's the case.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if echo "$SCRIPT_DIR" | grep -q ':'; then
    case "$OS" in
        Darwin) VENV="$HOME/Library/Application Support/stjude-generator/.venv" ;;
        *)      VENV="$HOME/.local/share/stjude-generator/.venv" ;;
    esac
    warn "Project path contains ':' — venv will be created at:"
    warn "  $VENV"
else
    VENV="$SCRIPT_DIR/.venv"
fi

# ── Create virtual environment ─────────────────────────────────────────────────
if [ -d "$VENV" ]; then
    warn "Virtual environment already exists — skipping creation."
else
    info "Creating virtual environment..."
    mkdir -p "$(dirname "$VENV")"
    "$PYTHON" -m venv "$VENV"
    success "Created $VENV"
fi

# ── Activate — path differs on Windows Git Bash vs Unix ───────────────────────
case "$OS" in
    MINGW*|MSYS*|CYGWIN*)
        ACTIVATE="$VENV/Scripts/activate"
        PIP_BIN="$VENV/Scripts/pip"
        PY_BIN="$VENV/Scripts/python"
        ;;
    *)
        ACTIVATE="$VENV/bin/activate"
        PIP_BIN="$VENV/bin/pip"
        PY_BIN="$VENV/bin/python"
        ;;
esac

# shellcheck source=/dev/null
source "$ACTIVATE"

# ── Install dependencies ───────────────────────────────────────────────────────
info "Installing dependencies..."
"$PIP_BIN" install --upgrade pip --quiet
"$PIP_BIN" install -r "$SCRIPT_DIR/requirements.txt" --quiet
success "Dependencies installed"

# ── Verify ─────────────────────────────────────────────────────────────────────
"$PY_BIN" -c "import tqdm" 2>/dev/null && success "tqdm OK" || warn "tqdm import failed — progress bars will be text-only"

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
success "Installation complete!"
echo ""
info "To run:"
echo "   source \"$ACTIVATE\""
echo "   cd \"$SCRIPT_DIR\""
echo "   python generate.py --help"
echo "   python generate.py --dry-run"
echo "   python generate.py --scale 0.01 --output /path/to/storage"
echo ""

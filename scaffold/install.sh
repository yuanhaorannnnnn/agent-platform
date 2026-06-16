#!/usr/bin/env bash
# =============================================================================
# dotfiles/install.sh — Bootstrap symlinks
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
BASHRC_SRC="$REPO_DIR/bash/bashrc"
BASHRC_DST="$HOME/.bashrc"
BIN_DIR="$REPO_DIR/bin"
LOCAL_BIN="$HOME/.local/bin"
BACKUP_DIR="$HOME/.bashrc-backups"

echo "📦 Dotfiles installer"
echo "   Repo: $REPO_DIR"
echo ""

# Backup existing ~/.bashrc if it's a real file (not already a symlink)
if [ -f "$BASHRC_DST" ] && [ ! -L "$BASHRC_DST" ]; then
    mkdir -p "$BACKUP_DIR"
    BACKUP_NAME="bashrc-$(date +%Y%m%d-%H%M%S)"
    cp "$BASHRC_DST" "$BACKUP_DIR/$BACKUP_NAME"
    echo "✅ Backed up existing ~/.bashrc → $BACKUP_DIR/$BACKUP_NAME"
fi

if [ -L "$BASHRC_DST" ]; then
    echo "🔄 Updating existing symlink ~/.bashrc"
    rm "$BASHRC_DST"
else
    echo "🔗 Creating symlink ~/.bashrc → $BASHRC_SRC"
fi
ln -s "$BASHRC_SRC" "$BASHRC_DST"

# Install all scripts from bin/ to ~/.local/bin/
if [ -d "$BIN_DIR" ]; then
    mkdir -p "$LOCAL_BIN"
    for src in "$BIN_DIR"/*; do
        [ -f "$src" ] || continue
        name=$(basename "$src")
        dst="$LOCAL_BIN/$name"

        chmod +x "$src"

        if [ -e "$dst" ] && [ ! -L "$dst" ]; then
            mkdir -p "$BACKUP_DIR"
            bak="$BACKUP_DIR/$name-$(date +%Y%m%d-%H%M%S)"
            cp "$dst" "$bak"
            echo "✅ Backed up existing $name → $bak"
        fi

        ln -sfn "$src" "$dst"
        echo "🔗 Installed $name → $src"
    done
fi

# Check secrets
echo ""
if [ ! -f "$REPO_DIR/bash/secrets" ]; then
    echo "⚠️  secrets file not found. Copy from template:"
    echo "   cp $REPO_DIR/bash/secrets.example $REPO_DIR/bash/secrets"
    echo "   Then edit $REPO_DIR/bash/secrets with your real keys."
else
    echo "✅ secrets file exists"
fi

echo ""
echo "🎉 Done."
echo ""

if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    echo "🔄 Reloading ~/.bashrc in current shell..."
    source ~/.bashrc
    echo "✅ Ready. Try: src, alias ls, kj"
else
    echo "⚠️  Current shell is NOT affected (install.sh ran in a subshell)."
    echo "   Run one of the following to apply:"
    echo ""
    echo "      source ~/.bashrc"
    echo "      . ~/.bashrc"
    echo "      exec bash"
    echo ""
fi

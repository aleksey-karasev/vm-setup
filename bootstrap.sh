#!/usr/bin/env bash

set -euo pipefail

REPO="${VM_SETUP_REPO:-https://github.com/aleksey-karasev/vm-setup.git}"
REF="${VM_SETUP_REF:-main}"
CHECKOUT="${VM_SETUP_DIR:-$HOME/.local/share/vm-setup}"
MACHINE_VARS="$HOME/.config/vm-setup/vars.yml"

remember() {
  mkdir -p "$(dirname "$MACHINE_VARS")"
  touch "$MACHINE_VARS"
  if grep -q "^$1:" "$MACHINE_VARS"; then
    sed -i.bak "s/^$1:.*/$1: $2/" "$MACHINE_VARS"
  else
    [ -z "$(tail -c1 "$MACHINE_VARS")" ] || echo >>"$MACHINE_VARS"
    echo "$1: $2" >>"$MACHINE_VARS"
  fi
}

main() {
  # The alternate array expansions below also work with macOS's Bash 3.2 and -u.
  local pull_args=() sudo=() arg
  local system
  system="$(uname -s)"

  for arg in "$@"; do
    case "$arg" in
      --nvidia) remember nvidia_enabled true ;;
      --no-nvidia) remember nvidia_enabled false ;;
      *) pull_args+=("$arg") ;;
    esac
  done

  if [ "$system" = Darwin ]; then
    if [ "$(id -u)" -eq 0 ]; then
      echo "Run vm-setup as your macOS user; Homebrew cannot run as root." >&2
      return 1
    fi
    # Find standard Homebrew installations even in a fresh login shell.
    if ! command -v brew >/dev/null; then
      for arg in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [ -x "$arg" ]; then
          eval "$("$arg" shellenv)"
          break
        fi
      done
    fi
    if ! command -v brew >/dev/null; then
      sudo -v
      NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      if [ -x /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
      else
        eval "$(/usr/local/bin/brew shellenv)"
      fi
    fi
    eval "$(brew shellenv)"
  elif [ "$(id -u)" -ne 0 ]; then
    sudo=(sudo)
    sudo -k -n true 2>/dev/null || pull_args+=(--ask-become-pass)
  fi

  if ! command -v ansible-pull >/dev/null || ! command -v git >/dev/null; then
    if [ "$system" = Darwin ]; then
      brew install ansible git
    elif [ -e /etc/arch-release ]; then
      ${sudo[@]+"${sudo[@]}"} pacman -Syu --needed --noconfirm ansible-core git curl ca-certificates
    elif [ -e /etc/fedora-release ]; then
      ${sudo[@]+"${sudo[@]}"} dnf install -y ansible-core git /usr/bin/curl ca-certificates python3-libdnf5
    else
      ${sudo[@]+"${sudo[@]}"} apt-get update
      ${sudo[@]+"${sudo[@]}"} env DEBIAN_FRONTEND=noninteractive \
        apt-get install -y ansible-core git curl ca-certificates
    fi
  fi

  ANSIBLE_HOST_PATTERN_MISMATCH=ignore \
    ansible-pull --full --url "$REPO" --checkout "$REF" --directory "$CHECKOUT" ${pull_args[@]+"${pull_args[@]}"} local.yml

  echo "Done. Log out and back in to pick up PATH and group changes."
}

main "$@"

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
    sed -i "s/^$1:.*/$1: $2/" "$MACHINE_VARS"
  else
    [ -z "$(tail -c1 "$MACHINE_VARS")" ] || echo >>"$MACHINE_VARS"
    echo "$1: $2" >>"$MACHINE_VARS"
  fi
}

main() {
  local pull_args=() sudo=() arg

  for arg in "$@"; do
    case "$arg" in
      --nvidia) remember nvidia_enabled true ;;
      --no-nvidia) remember nvidia_enabled false ;;
      *) pull_args+=("$arg") ;;
    esac
  done

  if [ "$(id -u)" -ne 0 ]; then
    sudo=(sudo)
    sudo -k -n true 2>/dev/null || pull_args+=(--ask-become-pass)
  fi

  if ! command -v ansible-pull >/dev/null || ! command -v git >/dev/null; then
    "${sudo[@]}" apt-get update
    "${sudo[@]}" env DEBIAN_FRONTEND=noninteractive \
      apt-get install -y ansible-core git curl ca-certificates
  fi

  ANSIBLE_HOST_PATTERN_MISMATCH=ignore \
    ansible-pull --url "$REPO" --checkout "$REF" --directory "$CHECKOUT" "${pull_args[@]}" local.yml

  echo "Done. Log out and back in to pick up PATH and group changes."
}

main "$@"

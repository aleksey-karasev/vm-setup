#!/usr/bin/env bash

set -euo pipefail

texlive=true
nvidia=false
for arg in "$@"; do
  case "$arg" in
    --no-texlive) texlive=false ;;
    --nvidia) nvidia=true ;;
  esac
done

check() {
  echo "+ $*"
  "$@" >/dev/null
}

for py in 3.9 3.10 3.11 3.12 3.13 3.14; do
  check "python$py" --version
done

for tool in ruff ty pytest cookiecutter pre-commit crewai mlflow httpx2 hf fastapi typer \
            ipython kaggle marimo mkdocs whisper rip uvicorn yt-dlp markitdown; do
  check "$tool" --help
done
check jupyter lab --version

for tool in uv pnpm node rtk rclone claude duckdb lazydocker starship gh docker rg fd bat duf \
            eza fzf jq tree hyperfine sqlite3 wget rsync gcc make cmake pkg-config vd \
            inkscape pandoc procs dust btop chromium; do
  check "$tool" --version
done
check ffmpeg -version
check dot -V
check tmux -V
check 7z i
check zip -v
check git lfs version
check git config --global --get filter.lfs.process
check docker compose version
check systemctl is-active docker
if [ -e /etc/arch-release ]; then
  check pacman -Q drawio-desktop
  check test -f /usr/share/bash-completion/bash_completion
else
  check snap list drawio
fi

if $texlive; then
  check pdflatex --version
fi

if $nvidia; then
  check nvcc --version
  check nvidia-ctk --version
  check nvtop --version
  check grep nvidia-container-runtime /etc/docker/daemon.json
fi

check diff "$(dirname "$0")/../files/starship.toml" ~/.config/starship.toml

check bash -ic 'declare -F starship_precmd'
echo "+ starship prompt (no warnings)"
starship_warnings="$(cd && starship prompt 2>&1 >/dev/null)"
[ -z "$starship_warnings" ] || { echo "$starship_warnings"; exit 1; }
check bash -ic '[ "$HISTSIZE" = 100000 ] && shopt -q histappend'
echo "+ bash keeps a history file longer than 2000 lines"
history_file="$(mktemp)"
seq 3000 >"$history_file"
HISTFILE="$history_file" bash -ic true 2>/dev/null
[ "$(wc -l <"$history_file")" = 3000 ]
check bash -ic 'declare -F __fzf_history__'
echo "+ fc-list | grep 'JetBrainsMono Nerd Font'"
fc-list | grep 'JetBrainsMono Nerd Font' >/dev/null
echo "All checks passed."

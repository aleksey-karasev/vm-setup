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

for tool in uv pnpm node rtk rclone claude duckdb starship gh docker rg fd bat duf \
            inkscape pandoc procs dust btop chromium; do
  check "$tool" --version
done
check ffmpeg -version
check docker compose version
check systemctl is-active docker
check snap list drawio

if $texlive; then
  check pdflatex --version
fi

if $nvidia; then
  check nvcc --version
  check nvidia-ctk --version
  check grep nvidia-container-runtime /etc/docker/daemon.json
fi

check diff "$(dirname "$0")/../files/starship.toml" ~/.config/starship.toml

check bash -ic 'declare -F starship_precmd'
echo "+ fc-list | grep 'JetBrainsMono Nerd Font'"
fc-list | grep 'JetBrainsMono Nerd Font' >/dev/null
echo "All checks passed."

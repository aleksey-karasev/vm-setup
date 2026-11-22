#!/usr/bin/env bash

set -euo pipefail
umask 077

test_directory="$(mktemp -d)"
cleanup() {
  tmux -S "$test_directory/tmux.sock" kill-server 2>/dev/null || true
  rm -rf "$test_directory"
}
trap cleanup EXIT

for tool in curl wget git delta shellcheck sqlite3 micro yq vd visidata harlequin; do
  echo "+ $tool --version"
  "$tool" --version >/dev/null
done
ssh -V
ssh -T -F /dev/null -G localhost >"$test_directory/ssh-config"
tmux -V
dig -v
lsof -nP -a -p "$$" -d cwd >/dev/null

if [[ "$(uname -s)" == Linux ]]; then
  PATH="$PATH:/usr/sbin:/sbin"
  command -v iptables
  command -v ufw
fi
mtr --version
fail2ban-client --version
netstat -rn >/dev/null

git -c init.defaultBranch=main init --quiet "$test_directory/git"
test -z "$(git -C "$test_directory/git" status --porcelain)"
test "$(sqlite3 "$test_directory/data.sqlite" \
  'CREATE TABLE numbers (value INTEGER); INSERT INTO numbers VALUES (20), (22); SELECT SUM(value) FROM numbers;')" = 42

case "$(yq --version)" in
  *github.com/mikefarah/yq/*) ;;
  *) echo "Expected Mike Farah's yq" >&2; exit 1 ;;
esac
printf 'tool: vm-setup\ncount: 2\n' >"$test_directory/data.yml"
test "$(yq '.tool' "$test_directory/data.yml")" = vm-setup
yq -i '.count += 40' "$test_directory/data.yml"
yq -o=json '.' "$test_directory/data.yml" >"$test_directory/data.json"
test "$(yq '.count' "$test_directory/data.json")" = 42

printf 'name,value\nfirst,20\nsecond,22\n' >"$test_directory/data.csv"
printf 'name\tvalue\nfirst\t20\nsecond\t22\n' >"$test_directory/expected.tsv"
vd --config /dev/null --batch "$test_directory/data.csv" --output "$test_directory/data.tsv"
diff "$test_directory/expected.tsv" "$test_directory/data.tsv"

tmux -S "$test_directory/tmux.sock" -f /dev/null new-session -d -s vm-setup-test 'sleep 60'
tmux -S "$test_directory/tmux.sock" has-session -t vm-setup-test
tmux -S "$test_directory/tmux.sock" kill-server

harlequin --help >/dev/null
harlequin_python="$(uv tool dir)/harlequin/bin/python"
"$harlequin_python" "$(dirname "$0")/check_harlequin.py"

echo "CLI installation and functional checks passed."

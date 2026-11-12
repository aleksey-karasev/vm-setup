#!/usr/bin/env bash

set -euo pipefail
umask 077

test_directory="$(mktemp -d)"
trap 'rm -rf "$test_directory"' EXIT
# Resolve macOS's /var and /tmp symlinks so restored absolute paths match.
test_directory="$(cd "$test_directory" && pwd -P)"

# Keep the test independent of the user's restic repository and credentials.
unset RESTIC_REPOSITORY_FILE RESTIC_PASSWORD RESTIC_PASSWORD_COMMAND RESTIC_KEY_HINT
export RESTIC_REPOSITORY="$test_directory/repository"
export RESTIC_PASSWORD_FILE="$test_directory/password"
export RESTIC_CACHE_DIR="$test_directory/cache"
printf 'vm-setup-restic-test-password\n' >"$RESTIC_PASSWORD_FILE"

mkdir -p "$test_directory/source/nested"
printf 'first version\n' >"$test_directory/source/message.txt"
printf 'nested file\n' >"$test_directory/source/nested/file.txt"
cp -R "$test_directory/source" "$test_directory/expected-first"

restic version
restic init
restic backup "$test_directory/source" --tag first
printf 'second version\n' >"$test_directory/source/message.txt"
printf 'added file\n' >"$test_directory/source/added.txt"
restic backup "$test_directory/source" --tag second
restic check --read-data

restic restore latest --tag first --target "$test_directory/restored-first"
diff -r "$test_directory/expected-first" "$test_directory/restored-first$test_directory/source"
restic restore latest --tag second --target "$test_directory/restored-second"
diff -r "$test_directory/source" "$test_directory/restored-second$test_directory/source"

echo "Restic backup and restore checks passed."

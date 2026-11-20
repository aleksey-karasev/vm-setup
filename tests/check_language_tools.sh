#!/usr/bin/env bash

set -euo pipefail

test_directory="$(mktemp -d)"
trap 'rm -rf "$test_directory"' EXIT

go version
rustc --version
cargo --version

(
  mkdir "$test_directory/go"
  cd "$test_directory/go"
  export GOENV=off GOWORK=off GOTOOLCHAIN=local GOPROXY=off
  export GOCACHE="$test_directory/go-cache" GOBIN="$test_directory/bin"
  go mod init example.com/vm-setup-test
  cat >main.go <<'EOF'
package main

import "fmt"

func main() {
	fmt.Println(42)
}
EOF
  go install .
  output="$("$GOBIN/vm-setup-test")"
  test "$output" = 42
)

(
  cd "$test_directory"
  export CARGO_HOME="$test_directory/cargo-home"
  cargo new --quiet --vcs none rust-test
  cd rust-test
  printf '%s\n' 'fn main() { println!("42"); }' >src/main.rs
  output="$(cargo run --offline --quiet)"
  test "$output" = 42
)

echo "Go and Rust toolchain checks passed."

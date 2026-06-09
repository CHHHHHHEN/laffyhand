#!/bin/sh
msg=$(cat "$1")

echo "$msg" | grep -qE '^(Merge|Revert|fixup!|squash!)' && exit 0

echo "$msg" | grep -qE '^[a-z]+\([a-z_/+-]+\): .{1,72}$' ||
  echo "$msg" | grep -qE '^[a-z]+\([a-z_/+-]+\)!: .{1,72}$' || {
    echo "ERROR: Commit message must match: type(scope): message"
    echo "  types: feat|fix|refactor|chore|docs|test|style|perf|revert"
    exit 1
  }

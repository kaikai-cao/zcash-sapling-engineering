#!/usr/bin/env bash
# Sensitive-path guard for the Sapling engineering repository.
#
# `wallet.db.sealed` is a byte-for-byte copy of the regtest `zallet/wallet.db`
# and contains spending keys. FREEZE.md (PR #24) declares it, together with the
# rest of MANIFEST.local-excluded.sha256, as local-only evidence that must never
# be committed, even on regtest/testnet.
#
# This guard inspects the *tracked* file set, so it also catches files that were
# force-added past .gitignore. It does not rewrite history; if it fires, remove
# the paths AND clean the history/remote objects before merging.
set -euo pipefail

PATTERN='(^|/)(wallet\.db|wallet\.db\.sealed|[^/]*\.sealed|\.cookie|MANIFEST\.local-excluded\.sha256)$|(^|/)run_[^/]*/run\.log$|(^|/)_note_scan_diag/|(^|/)laststate_seal_[^/]*/(filelist\.tsv|sha256\.txt)$'

bad="$(git ls-files | grep -E "$PATTERN" || true)"

if [[ -n "$bad" ]]; then
  echo "::error::sensitive / local-excluded files are tracked by git:" >&2
  printf '%s\n' "$bad" >&2
  echo "Do not merge. See experiments/e2e_testnet_tx/FREEZE.md (wallet upload boundary)." >&2
  exit 1
fi

echo "sensitive-path guard: clean ($(git ls-files | wc -l) tracked files)"

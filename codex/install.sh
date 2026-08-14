#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
codex_root="${CODEX_HOME:-$HOME/.codex}"
target="$codex_root/skills"

mkdir -p "$target"
cp -R "$repo_root/skills/." "$target/"
cp -R "$repo_root/codex/skills/." "$target/"

printf 'Instalado em %s\n' "$target/executar-plano-codex"

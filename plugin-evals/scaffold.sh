#!/usr/bin/env bash
# Prepare the eval session's working directory.
#
#   scaffold.sh [<fixture>|none] [stage-traces] [stage-profiles] [stage-plans]
#
# Fixtures live in tests/fixtures/projects/ (a vault-like MCP-on-Lambda project,
# good and bad gateways, a Strands agent, a broken MCP runtime, a starter-toolkit
# project). `none` copies no project, for cases that only need staged data.
#
# Staging directives copy read-only fixture data into ./fixtures/ so a prompt
# can use a sandbox-relative path:
#   stage-traces    tests/fixtures/traces   -> ./fixtures/traces
#   stage-profiles  tests/fixtures/profiles -> ./fixtures/profiles
#   stage-plans     tests/fixtures/plans    -> ./fixtures/plans
#
# It also writes ./.scaffold/: manifest.txt records what ran, protected.sha256
# the checksum of every Terraform file a case must not modify.
#
# Requires `claude plugin eval --scaffold`; scaffold scripts are opt-in.
set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fixture=""
staged=""
for arg in "$@"; do
  case "${arg}" in
    stage-traces|stage-profiles|stage-plans)
      kind="${arg#stage-}"
      mkdir -p "./fixtures/${kind}"
      cp -R "${plugin_root}/tests/fixtures/${kind}/." "./fixtures/${kind}/"
      staged="${staged} ${kind}"
      ;;
    *)
      if [[ -z "${fixture}" ]]; then
        fixture="${arg}"
      else
        echo "unexpected argument: ${arg}" >&2
        exit 2
      fi
      ;;
  esac
done
fixture="${fixture:-vault_like}"

if [[ "${fixture}" != "none" ]]; then
  source_dir="${plugin_root}/tests/fixtures/projects/${fixture}"
  if [[ ! -d "${source_dir}" ]]; then
    echo "no such fixture project: ${fixture}" >&2
    exit 2
  fi
  cp -R "${source_dir}/." .
fi

mkdir -p .scaffold
{
  echo "fixture=${fixture}"
  echo "staged=${staged# }"
} > .scaffold/manifest.txt

: > .scaffold/protected.sha256
while IFS= read -r -d '' file; do
  python3 - "${file}" >> .scaffold/protected.sha256 <<'PY'
import hashlib, sys
path = sys.argv[1]
print(f"{hashlib.sha256(open(path, 'rb').read()).hexdigest()}  {path}")
PY
done < <(find . -name '*.tf' -not -path './.scaffold/*' -print0)

echo "scaffolded ${fixture} (staged:${staged:-" none"}) into $(pwd)"

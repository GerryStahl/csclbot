#!/usr/bin/env bash
# DRAFT, NOT RUN. Downloads the cloud usage log into data/logs/ so that
# `.venv/bin/python src/usage_report.py` (or Excel) can read it on this machine.
# Usage: SA=stcsclbot<suffix> deploy/fetch_logs.sh      (after `az login`)
set -euo pipefail
SA="${SA:?set SA to the storage account name printed by deploy.sh}"
mkdir -p data/logs
az storage file download --account-name "$SA" --share-name state --path logs/usage.csv \
  --dest data/logs/usage.csv --auth-mode login --overwrite true
echo "Saved data/logs/usage.csv; run: .venv/bin/python src/usage_report.py"

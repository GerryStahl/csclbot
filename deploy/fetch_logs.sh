#!/usr/bin/env bash
# Downloads the cloud usage log into data/logs/ so that
# `.venv/bin/python src/usage_report.py` (or Excel) can read it on this machine.
# Usage: deploy/fetch_logs.sh      (after `az login`; defaults to the account created by deploy.sh)
set -euo pipefail
SA="${SA:-stcsclbotgs7k2}"
RG="${RG:-rg-csclbot}"
export AZURE_CORE_ONLY_SHOW_ERRORS=true PYTHONWARNINGS=ignore
KEY=$(az storage account keys list -g "$RG" -n "$SA" --query "[0].value" -o tsv)
mkdir -p data/logs
az storage file download --account-name "$SA" --share-name state --path logs/usage.csv \
  --dest data/logs/usage.csv --account-key "$KEY" >/dev/null
echo "Saved data/logs/usage.csv; run: .venv/bin/python src/usage_report.py"

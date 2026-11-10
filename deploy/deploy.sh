#!/usr/bin/env bash
# DRAFT, NOT RUN. Deploys CSCLbot to Azure Container Apps. Nothing here has been executed yet;
# review documentation/deployment.md first, and fill the variables below. Commands were written
# from memory of the az CLI and will be checked step by step on the first real run.
#
# Prerequisites: Azure CLI (brew install azure-cli), `az login`, ANTHROPIC_API_KEY exported in this shell.
# The key is passed to Azure as a secret from the environment; it is never written to a file or printed.
set -euo pipefail
set +x   # never trace: the script handles secrets (do not run it with bash -x)
umask 077
export AZURE_CORE_ONLY_SHOW_ERRORS=true PYTHONWARNINGS=ignore
RENDERED="$(mktemp)"
trap 'rm -f "$RENDERED"' EXIT   # the rendered file contains secrets

SUBSCRIPTION="${SUBSCRIPTION:?set SUBSCRIPTION to the subscription id or name}"
LOCATION="${LOCATION:-eastus}"
RG="${RG:-rg-csclbot}"
SUFFIX="${SUFFIX:?set SUFFIX to a short unique string (lower case letters/digits) for globally unique names}"
ACR="acrcsclbot${SUFFIX}"
SA="stcsclbot${SUFFIX}"
ENV_NAME="cae-csclbot"
APP="csclbot"
LAW="log-csclbot"
TAG="${TAG:-$(date +%Y%m%d-%H%M)}"
MIN_REPLICAS="${MIN_REPLICAS:-0}"   # 0 = scale to zero (cheap, first visitor waits ~1 min); 1 = always on
: "${ANTHROPIC_API_KEY:?export ANTHROPIC_API_KEY first}"

az account set --subscription "$SUBSCRIPTION"
az extension add --name containerapp --upgrade -y
# a new subscription must register each service once
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry Microsoft.Storage; do
  az provider register --namespace "$ns" --wait
done

az group create -n "$RG" -l "$LOCATION"

# 1. Registry and cloud image build (no local Docker needed)
az acr create -g "$RG" -n "$ACR" --sku Basic --admin-enabled true
if [ -z "${SKIP_BUILD:-}" ]; then   # SKIP_BUILD=1 TAG=<existing tag> reuses an image that is already built
  az acr build -r "$ACR" -t "csclbot:$TAG" .
fi

# 2. Logging, environment, persistent storage for the usage log and spend counter
az monitor log-analytics workspace create -g "$RG" -n "$LAW" -l "$LOCATION"
LAW_ID=$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" --query customerId -o tsv)
LAW_KEY=$(az monitor log-analytics workspace get-shared-keys -g "$RG" -n "$LAW" --query primarySharedKey -o tsv)
az containerapp env create -g "$RG" -n "$ENV_NAME" -l "$LOCATION" --logs-workspace-id "$LAW_ID" --logs-workspace-key "$LAW_KEY"

az storage account create -g "$RG" -n "$SA" -l "$LOCATION" --sku Standard_LRS --allow-blob-public-access false
SA_KEY=$(az storage account keys list -g "$RG" -n "$SA" --query "[0].value" -o tsv)
az storage share-rm create -g "$RG" --storage-account "$SA" --name state --quota 5
az containerapp env storage set -g "$RG" -n "$ENV_NAME" --storage-name state \
  --azure-file-account-name "$SA" --azure-file-account-key "$SA_KEY" --azure-file-share-name state --access-mode ReadWrite

# 3. The app (secrets come from this shell's environment)
export RG ENV_NAME APP MIN_REPLICAS LOCATION SUBSCRIPTION
export ACR_SERVER="${ACR}.azurecr.io"
export ACR_USER=$(az acr credential show -n "$ACR" --query username -o tsv)
export ACR_PASSWORD=$(az acr credential show -n "$ACR" --query "passwords[0].value" -o tsv)
export IMAGE="${ACR_SERVER}/csclbot:${TAG}"
export HASH_SALT=$(python3 -c "import secrets; print(secrets.token_hex(16))")
export ENV_ID=$(az containerapp env show -g "$RG" -n "$ENV_NAME" --query id -o tsv)
envsubst < deploy/containerapp.yaml > "$RENDERED"
az containerapp create -g "$RG" -n "$APP" --yaml "$RENDERED"

az containerapp show -g "$RG" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv | sed 's|^|https://|'
echo "Storage account for logs: $SA (share: state)"

#!/usr/bin/env bash
# ==============================================================================
# CREATE THE FUNCTION APP THAT RUNS THE PIPELINE WHEN A PDF LANDS
# ==============================================================================
# Run from the project folder, after provision.sh has created the resources:
#
#     export SUFFIX=12345                       # the same number provision.sh used
#     export RESOURCE_GROUP=rg-supply-chain-rag
#     export STORAGE=stsupplychain12345         # the storage account provision.sh made
#     bash azure_setup/provision-function.sh
#
# WHAT IT DOES
#   1. creates a Linux, Python 3.11, Consumption-plan function app
#      func-supplychain-<SUFFIX>
#   2. creates the two extra containers the trigger writes to
#      (supply-chain-markdown and supply-chain-results)
#   3. copies the .env values into the app's settings -- read with
#      `set -a; source .env`, never printed
#   4. calls deploy-function.sh, which installs the Linux packages on this Mac,
#      zips the code and uploads it. The remote build is switched off, because
#      it never installed the packages on this Linux Consumption app.
#
# WHY SUFFIX IS REQUIRED HERE
#   provision.sh invents a random SUFFIX when you do not give one. This script
#   must use the SAME number, or it would name the function app after a
#   resource group that does not exist. So it stops and asks instead of guessing.
#
# THIS COSTS MONEY while it exists (Consumption plan: per execution, plus the
# storage it uses). teardown.sh deletes the whole resource group, function app
# included -- nothing extra to remove.
# ==============================================================================

set -euo pipefail                               # stop at the first error; treat unset variables as errors

# --- names: the same pattern provision.sh uses ---------------------------------
SUFFIX="${SUFFIX:?Set SUFFIX to the same value provision.sh used (it is in every resource name)}"
LOCATION="${LOCATION:-eastus2}"                 # the region provision.sh used
RG="${RESOURCE_GROUP:?Set RESOURCE_GROUP, e.g. rg-supply-chain-rag}"          # the resource group holding everything
STORAGE="${STORAGE:?Set STORAGE to the storage account name, e.g. stsupplychain12345}"
OPENAI="${OPENAI:-aoai-supplychain-$SUFFIX}"    # Azure OpenAI resource name, as provision.sh named it
SEARCH="${SEARCH:-srch-supplychain-$SUFFIX}"    # Azure AI Search service name, as provision.sh named it
FUNC="func-supplychain-$SUFFIX"                 # the function app this script creates

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"     # the project folder: this script's folder, one level up
cd "$PROJECT"                                   # work from there, wherever the script was started

echo "Creating function app $FUNC (Linux, Python 3.11, Consumption plan)"
az functionapp create --name "$FUNC" --resource-group "$RG" --storage-account "$STORAGE" \
  --consumption-plan-location "$LOCATION" --runtime python --runtime-version 3.11 \
  --functions-version 4 --os-type Linux --output none   # Consumption: no plan to create, billed per execution

# --- the two containers the trigger writes to ---------------------------------
echo "Reading .env (values are used, never printed)"
while IFS= read -r line || [ -n "$line" ]; do  # read .env line by line (values contain ';' so we cannot 'source' it)
  case "$line" in ''|\#*) continue ;; esac       # skip blank lines and comments
  export "${line%%=*}=${line#*=}"                 # split at the FIRST '=' only
done < .env

MARKDOWN="${AZURE_MARKDOWN_CONTAINER:-supply-chain-markdown}"   # markdown of each new PDF
RESULTS="${AZURE_RESULTS_CONTAINER:-supply-chain-results}"      # the agent's answer about it

echo "Creating containers $MARKDOWN and $RESULTS"
az storage container create --name "$MARKDOWN" --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --output none
az storage container create --name "$RESULTS" --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --output none

# --- the app's settings: everything the pipeline reads from the environment ----
echo "Copying the .env values into the app settings of $FUNC"
az functionapp config appsettings set --name "$FUNC" --resource-group "$RG" --settings \
  "AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT" \
  "AZURE_OPENAI_API_KEY=$AZURE_OPENAI_API_KEY" \
  "AZURE_OPENAI_API_VERSION=$AZURE_OPENAI_API_VERSION" \
  "AZURE_OPENAI_GENERATION_DEPLOYMENT=$AZURE_OPENAI_GENERATION_DEPLOYMENT" \
  "AZURE_OPENAI_GUARDRAIL_DEPLOYMENT=$AZURE_OPENAI_GUARDRAIL_DEPLOYMENT" \
  "AZURE_OPENAI_FAST_DEPLOYMENT=$AZURE_OPENAI_FAST_DEPLOYMENT" \
  "AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$AZURE_OPENAI_EMBEDDING_DEPLOYMENT" \
  "AZURE_SEARCH_ENDPOINT=$AZURE_SEARCH_ENDPOINT" \
  "AZURE_SEARCH_API_KEY=$AZURE_SEARCH_API_KEY" \
  "AZURE_SEARCH_INDEX=$AZURE_SEARCH_INDEX" \
  "AZURE_STORAGE_CONNECTION_STRING=$AZURE_STORAGE_CONNECTION_STRING" \
  "AZURE_STORAGE_CONTAINER=$AZURE_STORAGE_CONTAINER" \
  "AZURE_MARKDOWN_CONTAINER=$MARKDOWN" \
  "AZURE_RESULTS_CONTAINER=$RESULTS" \
  "BLOB_TRIGGER_PATH=$AZURE_STORAGE_CONTAINER/{name}" \
  "SCM_DO_BUILD_DURING_DEPLOYMENT=false" \
  "ENABLE_ORYX_BUILD=false" \
  --output none                                 # --output none: no table of every setting echoed back

# --- the code ------------------------------------------------------------------
echo "Deploying the code"
RESOURCE_GROUP="$RG" FUNC_NAME="$FUNC" bash azure_setup/deploy-function.sh  # zip, upload, done

cat <<EOF

================================================================================
Done. Function app: $FUNC
  Blob trigger   $AZURE_STORAGE_CONTAINER/{name}   -> markdown, index, answer
  HTTP trigger   https://$FUNC.azurewebsites.net/api/run?code=<function key>
================================================================================
Remember: bash azure_setup/teardown.sh when you are finished, to stop charges.
EOF

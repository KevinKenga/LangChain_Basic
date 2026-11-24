#!/usr/bin/env bash
# fill-env.sh - asks Azure for the keys and writes them into .env, without printing them.
# Run it from the project folder:  bash azure_setup/fill-env.sh
# It only fills in the Azure values. Your other .env lines are kept.
set -euo pipefail

SUFFIX="${SUFFIX:-12345}"                       # the lucky number you chose when you created the resources
RG="${RG:-rg-supply-chain-rag}"                 # the resource group that holds everything
OPENAI="aoai-supplychain-$SUFFIX"               # Azure OpenAI resource name
SEARCH="srch-supplychain-$SUFFIX"               # Azure AI Search service name
STORAGE="stsupplychain$SUFFIX"                  # storage account name

[ -f .env ] || cp .env.example .env             # make sure the file exists

export AOAI_ENDPOINT AOAI_KEY SEARCH_KEY STORAGE_CONN
AOAI_ENDPOINT=$(az cognitiveservices account show --name "$OPENAI" --resource-group "$RG" --query properties.endpoint -o tsv)
AOAI_KEY=$(az cognitiveservices account keys list --name "$OPENAI" --resource-group "$RG" --query key1 -o tsv)
SEARCH_KEY=$(az search admin-key show --service-name "$SEARCH" --resource-group "$RG" --query primaryKey -o tsv)
STORAGE_CONN=$(az storage account show-connection-string --name "$STORAGE" --resource-group "$RG" --query connectionString -o tsv)

python3 - <<'PY'
import os, re

values = {
    "AZURE_OPENAI_ENDPOINT": os.environ["AOAI_ENDPOINT"],
    "AZURE_OPENAI_API_KEY": os.environ["AOAI_KEY"],
    "AZURE_OPENAI_API_VERSION": "2025-04-01-preview",
    "AZURE_OPENAI_GENERATION_DEPLOYMENT": "gpt-5.1",
    "AZURE_OPENAI_GUARDRAIL_DEPLOYMENT": "gpt-5.1",
    "AZURE_OPENAI_FAST_DEPLOYMENT": "gpt-5.1",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
    "AZURE_SEARCH_ENDPOINT": "https://srch-supplychain-%s.search.windows.net" % os.environ.get("SUFFIX", "12345"),
    "AZURE_SEARCH_API_KEY": os.environ["SEARCH_KEY"],
    "AZURE_SEARCH_INDEX": "supply-chain",
    "AZURE_STORAGE_CONNECTION_STRING": os.environ["STORAGE_CONN"],
    "AZURE_STORAGE_CONTAINER": "supply-chain-docs",
    "AZURE_MARKDOWN_CONTAINER": "supply-chain-markdown",
    "AZURE_RESULTS_CONTAINER": "supply-chain-results",
    "LOCAL_PDF_DIR": "./data/raw",
}

lines = open(".env").read().splitlines()
seen = set()
out = []
for line in lines:
    m = re.match(r"([A-Z_]+)=", line)
    if m and m.group(1) in values:
        out.append("%s=%s" % (m.group(1), values[m.group(1)]))
        seen.add(m.group(1))
    else:
        out.append(line)
for key, val in values.items():
    if key not in seen:
        out.append("%s=%s" % (key, val))
open(".env", "w").write("\n".join(out) + "\n")

print("Checked .env (values are hidden):")
for key in values:
    state = "filled" if values[key] else "EMPTY"
    print("  %-40s %s" % (key, state))
PY

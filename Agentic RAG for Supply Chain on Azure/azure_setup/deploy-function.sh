#!/usr/bin/env bash
# ==============================================================================
# SEND THE FUNCTION APP'S CODE TO AZURE
# ==============================================================================
# Called by provision-function.sh, and by hand after every code change:
#
#     RESOURCE_GROUP=rg-supply-chain-rag FUNC_NAME=func-supplychain-12345 \
#       bash azure_setup/deploy-function.sh
#
# WHAT PROBLEM DOES IT SOLVE
#   The function app needs the project's code, but not the things that must
#   never leave your laptop (.env, local.settings.json with its keys) and not
#   the things it does not need (the PDFs, the markdown cache, the tests, the
#   virtual environment, the set-up scripts). Zipping by hand makes it easy to
#   include the wrong file. This script always leaves them out.
#
# WHAT IT DOES
#   1. builds a temporary folder containing:
#        function_app/*        at the ROOT, because Azure looks for the entry
#                              point there (host.json, function_app.py, ...)
#        config.py, azure_clients.py, telemetry.py
#        ingestion/, graph/, retrieval/, guardrails/
#      and nothing else: no __pycache__, no data/, no tests/, no .env
#   2. installs the Linux packages into that folder, on this Mac, under
#        .python_packages/lib/site-packages
#      Azure's own remote build never installed them on this Linux Consumption
#      app: the function list stayed empty and every HTTP call returned
#      nothing. So the install happens here, and the zip carries the result.
#   3. zips that folder -- about 90 MB now that the packages are inside
#   4. switches the remote build off, so Azure does not try to install
#      anything a second time:
#        SCM_DO_BUILD_DURING_DEPLOYMENT=false  ENABLE_ORYX_BUILD=false
#   5. uploads it with `az functionapp deployment source config-zip`.
#      The upload takes 3 to 5 minutes: do not press Ctrl+C.
#
# HOW TO RUN (from the project folder, after az login)
#   RESOURCE_GROUP=rg-supply-chain-rag FUNC_NAME=func-supplychain-12345 bash azure_setup/deploy-function.sh
#
# EXPECTED OUTPUT
#   1. Packaging
#      Installing the Linux packages into the zip (this takes a minute or two)
#      90M zip
#   2. Switching the remote build off
#   3. Uploading (3 to 5 minutes; do not press Ctrl+C)
#   Done. Test it with the curl call in Section 9 of the guide: the first
#   reply of HTTP 200 is the real proof that the packages are inside.
# ==============================================================================

set -euo pipefail                               # stop at the first error; an unset variable is an error too

: "${RESOURCE_GROUP:?Set RESOURCE_GROUP}"       # stop with this message if RESOURCE_GROUP is not set
: "${FUNC_NAME:?Set FUNC_NAME}"                 # stop with this message if FUNC_NAME is not set

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"     # the project folder: this script's folder, one level up
cd "$PROJECT"                                   # work from there, wherever the script was started

echo "1. Packaging"
BUILD="$(mktemp -d)"                            # a new, empty temporary folder for the code
ZIP_DIR="$(mktemp -d)"                          # a second one, so the zip never contains itself
trap 'rm -rf "$BUILD" "$ZIP_DIR"' EXIT          # delete both when the script ends, whatever happens

cp -R function_app/. "$BUILD"/                  # the entry point: host.json and function_app.py at the root
cp config.py azure_clients.py telemetry.py "$BUILD"/   # the modules every other file imports
cp -R ingestion graph retrieval guardrails "$BUILD"/   # the pipeline itself

find "$BUILD" -name "__pycache__" -type d -prune -exec rm -rf {} +   # compiled bytecode is rebuilt on Azure
find "$BUILD" -name "*.pyc" -delete                                  # and so are the single files
rm -f "$BUILD/.env" "$BUILD/local.settings.json"                     # keys live in app settings, never in the zip

# --- the packages, installed here and carried inside the zip ------------------
# Azure's remote build never installed them on this Linux Consumption app, so
# the Linux wheels are installed on this Mac and shipped in the zip. --platform
# manylinux2014_x86_64 picks the Linux wheels rather than the macOS ones,
# --only-binary refuses to compile anything, and --target puts them exactly
# where Azure looks for them.
echo "   Installing the Linux packages into the zip (this takes a minute or two)"
PYTHON="$(command -v python || command -v python3)"   # python if this window has it, python3 otherwise
"$PYTHON" -m pip install -r function_app/requirements.txt \
    --target "$BUILD/.python_packages/lib/site-packages" \
    --platform manylinux2014_x86_64 --python-version 3.11 \
    --implementation cp --only-binary=:all: --upgrade --quiet

(cd "$BUILD" && zip -qr "$ZIP_DIR/function.zip" .)   # -q quiet, -r include sub-folders
echo "   $(du -h "$ZIP_DIR/function.zip" | cut -f1) zip"  # about 90 MB now: the Linux packages are inside

echo "2. Switching the remote build off"
az functionapp config appsettings set --name "$FUNC_NAME" --resource-group "$RESOURCE_GROUP" \
    --settings SCM_DO_BUILD_DURING_DEPLOYMENT=false ENABLE_ORYX_BUILD=false --output none
    # the packages are already in the zip, so Azure must not install them again

echo "3. Uploading (3 to 5 minutes; do not press Ctrl+C)"
az functionapp deployment source config-zip --name "$FUNC_NAME" --resource-group "$RESOURCE_GROUP" \
    --src "$ZIP_DIR/function.zip" --timeout 900 --output none
    # --timeout 900: a 90 MB zip needs longer than the default timeout

echo "Done. Watch the log stream with:"
echo "  az webapp log tail --name $FUNC_NAME --resource-group $RESOURCE_GROUP"

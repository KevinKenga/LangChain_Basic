# Azure Step by Step - Supply Chain Agentic RAG

A beginner's guide, on macOS, using bash. Every command is in a `bash` block,
with one line saying what it does and the result you should see afterwards.

Nothing here has been run against a real Azure subscription by the author of
this file: the commands follow the scripts in `azure_setup/`, but treat the
"expected result" lines as what the command is meant to print, and check the
portal if something looks different.

---

## 0. What you will build

```
   you upload a PDF                        a new PDF lands in the container
          |                                             |
          v                                             v
  supply-chain-docs  ------------------------>  blob trigger  on_new_pdf
   (PDF container)                               (Azure Function)
          |                                             |
          |                                             +--> PyMuPDF4LLM
          |                                             |      -> supply-chain-markdown/<name>.md
          |                                             +--> chunks + embeddings
          |                                             |      -> AI Search index "supply-chain"
          |                                             +--> LangGraph agent
          |                                                    -> supply-chain-results/<name>.answer.md
          |
   three ways to trigger it by hand:
     bash   python ingestion/process_blob.py <name>
     HTTP   POST https://func-supplychain-<SUFFIX>.azurewebsites.net/api/run?blob=<name>
     web    python UI/server.py   ->   http://127.0.0.1:8000
```

The pipeline itself (guardrails, router, retrieval, rerank, grade, generate,
grounding, human review) is unchanged. This guide only adds the two triggers
and the two extra containers they write to.

---

## 1. Prerequisites

**Install the Azure CLI.**

```bash
brew install azure-cli
```

Expected result: Homebrew installs `az`; the last line says something like
`Pouring azure-cli--2.x.x.arm64_sonoma.bottle.tar.gz`.

**Check the CLI answers.**

```bash
az version
```

Expected result: a small JSON block with `"azure-cli"` and `"azure-cli-core"`
version numbers.

**Check Python 3.11 and the project's virtual environment.** The environment
lives at `LangChain_Basic/.venv`, one folder above the project.

```bash
ls ../.venv/bin/python
```

Expected result: the path is printed, e.g. `../.venv/bin/python`. If it is
missing, create it once:

```bash
python3.11 -m venv ../.venv
```

Expected result: no output; a `.venv` folder appears next to the project.

**Check `zip`, which the deployment scripts use.**

```bash
zip --version | head -2
```

Expected result: a copyright line and a version such as `This is Zip 3.0`.

**Sign in to Azure.**

```bash
az login
```

Expected result: a browser opens; after signing in the terminal prints a JSON
list of your subscriptions.

**Check which subscription you are using.**

```bash
az account show --query name -o tsv
```

Expected result: your subscription's name, e.g. `My Azure Subscription`.

**Register the resource providers.** A new subscription has to be told about
each service family once. This takes a minute per provider and only needs
doing once per subscription.

```bash
az provider register --namespace Microsoft.CognitiveServices
az provider register --namespace Microsoft.Search
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.Web
az provider register --namespace Microsoft.Insights
```

Expected result: each command prints `Registering is still on-going. You can
monitor the status using 'az provider show -n <namespace>'` the first time.

**Check one of them finished.**

```bash
az provider show --namespace Microsoft.Web --query registrationState -o tsv
```

Expected result: `Registered`. If it says `Registering`, wait a minute and run
it again.

---

## 2. Go to the project and check it runs

The path has spaces and an `&`, so it must be quoted every time.

```bash
cd "/Users/msp/Desktop/TTU ONE DRIVE Copy/Bootcamps/AI&ML/Sep 27 Batch HandsOn/LangChain_Basic/Agentic RAG for Supply Chain on Azure"
```

Expected result: no output; `pwd` now shows that folder.

**Activate the virtual environment.**

```bash
source ../.venv/bin/activate
```

Expected result: your prompt gains a `(.venv)` prefix.

**Install the packages.**

```bash
pip install -r requirements.txt
```

Expected result: `Successfully installed ...` listing the Azure SDKs,
`langgraph`, `pymupdf4llm` and the rest.

**Run the offline tests.** They use fakes, so no Azure resource and no key is
needed.

```bash
python -m pytest -q
```

Expected result: `74 passed` (the number grows as tests are added; what matters
is that nothing fails).

---

## 3. The names, and how to keep them

Every resource has a fixed name except for a number, `SUFFIX`, which keeps the
globally unique names unique. `provision.sh` invents one if you do not give it
one, so pick your own and write it down.

| What | Name | Made by |
| --- | --- | --- |
| Resource group | `rg-supply-chain-rag` | `provision.sh` |
| Azure OpenAI resource | `aoai-supplychain-<SUFFIX>` | `provision.sh` |
| Deployment: answers | `gpt-4o` | `provision.sh` |
| Deployment: guardrails | `gpt-4o-mini` | `provision.sh` |
| Deployment: embeddings | `text-embedding-3-small` | `provision.sh` |
| Azure AI Search service | `srch-supplychain-<SUFFIX>` | `provision.sh` |
| Search index | `supply-chain` | `run_ingestion.py` |
| Storage account | `stsupplychain<SUFFIX>` | `provision.sh` |
| Container: PDFs | `supply-chain-docs` | `provision.sh` |
| Container: markdown | `supply-chain-markdown` | `provision-function.sh` |
| Container: agent answers | `supply-chain-results` | `provision-function.sh` |
| Function app | `func-supplychain-<SUFFIX>` | `provision-function.sh` |
| App Service plan | `plan-supplychain` | `hosting.md` |
| Web app | `supplychain-web-<SUFFIX>` | `hosting.md` |
| Log Analytics workspace | `log-supplychain` | `hosting.md` |
| Application Insights | `appi-supplychain` | `hosting.md` |

**Fix SUFFIX in this terminal.** Every later command reuses it.

```bash
export SUFFIX=12345
export LOCATION=eastus2
export RG=rg-supply-chain-rag
export STORAGE=stsupplychain$SUFFIX
echo "SUFFIX=$SUFFIX  <- write this down"
```

Expected result: `SUFFIX=12345  <- write this down`. A new terminal forgets
these, so run the block again with the same number.

---

## 4. Create the resources

### 4a. The one-command way

```bash
SUFFIX=$SUFFIX bash azure_setup/provision.sh
```

Expected result: a few `Creating ...` lines, then a block headed
`Done. Paste these lines into .env` with the endpoint, the two keys and the
connection string. It takes about ten minutes.

### 4b. The same thing, one command at a time

Use this if you want to see what each step does, or if the script stops
half-way.

**The resource group** - one folder that holds everything, and the one thing
`teardown.sh` deletes.

```bash
az group create --name "$RG" --location "$LOCATION" --output none
```

Expected result: no output. `az group exists --name "$RG"` now prints `true`.

**Azure OpenAI** - the resource that hosts the models.

```bash
az cognitiveservices account create --name "aoai-supplychain-$SUFFIX" --resource-group "$RG" \
  --location "$LOCATION" --kind OpenAI --sku S0 \
  --custom-domain "aoai-supplychain-$SUFFIX" --output none
```

Expected result: no output after a minute or two.

**The three deployments.** On Azure you call a deployment name, not a model
name, so each model is deployed under its own name.

```bash
az cognitiveservices account deployment create --name "aoai-supplychain-$SUFFIX" --resource-group "$RG" \
  --deployment-name gpt-4o --model-name gpt-4o --model-version 2024-11-20 --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 30 --output none
```

Expected result: no output.

```bash
az cognitiveservices account deployment create --name "aoai-supplychain-$SUFFIX" --resource-group "$RG" \
  --deployment-name gpt-4o-mini --model-name gpt-4o-mini --model-version 2024-07-18 --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 30 --output none
```

Expected result: no output.

```bash
az cognitiveservices account deployment create --name "aoai-supplychain-$SUFFIX" --resource-group "$RG" \
  --deployment-name text-embedding-3-small --model-name text-embedding-3-small --model-version 1 \
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 120 --output none
```

Expected result: no output. Check all three with
`az cognitiveservices account deployment list --name "aoai-supplychain-$SUFFIX" --resource-group "$RG" --query "[].name" -o tsv`.

**Azure AI Search, with the free semantic ranker.**

```bash
az search service create --name "srch-supplychain-$SUFFIX" --resource-group "$RG" --location "$LOCATION" \
  --sku basic --semantic-search free --output none
```

Expected result: no output after a few minutes. Basic is billed per hour; the
free semantic plan allows 1,000 reranked queries a month at no extra cost.

**Storage account and the PDF container.**

```bash
az storage account create --name "$STORAGE" --resource-group "$RG" --location "$LOCATION" \
  --sku Standard_LRS --allow-blob-public-access false --output none
```

Expected result: no output.

```bash
CONN=$(az storage account show-connection-string --name "$STORAGE" --resource-group "$RG" \
  --query connectionString --output tsv)
```

Expected result: no output; `$CONN` now holds the connection string. Do not
print it.

```bash
az storage container create --name supply-chain-docs --connection-string "$CONN" --output none
```

Expected result: no output. `az storage container list --connection-string "$CONN" --query "[].name" -o tsv`
now prints `supply-chain-docs`.

### 4c. Put the values in .env

```bash
cp .env.example .env
```

Expected result: no output; `.env` appears next to `.env.example`.

```bash
open -e .env
```

Expected result: TextEdit opens the file. Paste the block that `provision.sh`
printed, then save and close.

`.env` holds keys. It is already in `.gitignore`; never commit it.

**If your subscription only offers `gpt-5.1`**, leave the deployments as they
are and change the three deployment names in `.env` instead:

```bash
AZURE_OPENAI_GENERATION_DEPLOYMENT=gpt-5.1
AZURE_OPENAI_GUARDRAIL_DEPLOYMENT=gpt-5.1
AZURE_OPENAI_FAST_DEPLOYMENT=gpt-5.1
```

The embedding deployment must still be a real embedding model
(`text-embedding-3-small`), because the index is built for 512 numbers per
chunk.

---

## 5. Upload the PDFs and build the index

**Put the five PDFs in `data/raw/`** (or point `LOCAL_PDF_DIR` in `.env`
somewhere else).

```bash
ls data/raw
```

Expected result: the five file names, e.g. `sc_annual_review_fy2025.pdf`.

**Upload them to the PDF container.**

```bash
python ingestion/upload_pdfs.py
```

Expected result: one line per file, e.g. `sc_annual_review_fy2025.pdf  uploaded`.

**Download, convert, chunk, embed and upload in one go.**

```bash
python run_ingestion.py
```

Expected result: a chunk count per document, then `uploaded N of N chunks`.
This is the slow step: it embeds every chunk with Azure OpenAI.

**Check the index in the portal.** Open https://portal.azure.com, go to the
search service `srch-supplychain-<SUFFIX>`, then **Indexes** ->
`supply-chain` -> **Search explorer**, and run an empty search. Expected
result: a list of documents with `doc_type`, `fiscal_year` and `text`.

**Check the container with a command.**

```bash
az storage blob list --container-name supply-chain-docs --connection-string "$CONN" --query "[].name" -o tsv
```

Expected result: the five PDF names.

---

## 6. Run the agent by hand

**One question, at the keyboard.**

```bash
python run_query.py
```

Expected result: the router's plan, the retrieved chunks, the grounding
verdict, and then the answer. If grounding is low the graph pauses and asks
`approve or reject? [a/r]:`.

**The web page.**

```bash
python UI/server.py
```

Expected result: `Supply-chain RAG UI on http://127.0.0.1:8000   (Ctrl+C to stop)`.
Open http://127.0.0.1:8000 in a browser. Stop the server with Ctrl+C when you
are done.

**One file through the whole pipeline, from bash.** This is the same function
the blob trigger calls.

```bash
python ingestion/process_blob.py new_supplier_audit_fy2027.pdf
```

Expected result: a JSON block with `"status": "ok"`, `"markdown_blob":
"new_supplier_audit_fy2027.md"`, a `"chunks_indexed"` count and
`"answer_blob": "new_supplier_audit_fy2027.answer.md"`.

**Ingestion only, no agent.**

```bash
python ingestion/process_blob.py new_supplier_audit_fy2027.pdf --no-agent
```

Expected result: the same JSON, with `"agent_status": "skipped"` and
`"answer_blob": null`.

---

## 7. The automatic trigger

**Create the function app, the two containers and its settings, then deploy.**

```bash
SUFFIX=$SUFFIX RESOURCE_GROUP=$RG STORAGE=$STORAGE bash azure_setup/provision-function.sh
```

Expected result: `Creating function app func-supplychain-12345 ...`, then
`Deploying the code`, then `1. Packaging` with
`Installing the Linux packages into the zip`, then `2. Switching the remote
build off`, then `3. Uploading (3 to 5 minutes; do not press Ctrl+C)`, then a
block naming the blob trigger path and the HTTP address. The packages are
installed on your Mac and carried inside the zip (about 90 MB), because Azure's
remote build did not install them on this Linux Consumption app.

**Load the .env values into this shell without printing them.**

```bash
while IFS= read -r line || [ -n "$line" ]; do case "$line" in ''|\#*) continue ;; esac; export "${line%%=*}=${line#*=}"; done < .env
```

Expected result: no output. Each line is read whole and split at the first `=`
only. Never `source .env` (with or without `set -a`): the storage connection
string contains a `;`, so `source` stops there and the value arrives cut in
half. Never `echo` these values.

**Upload a new PDF to the PDF container.** Use any PDF you have; the name is
what the metadata is inferred from.

```bash
az storage blob upload --container-name supply-chain-docs \
  --file "data/raw/sc_annual_review_fy2026.pdf" \
  --name "new_supplier_audit_fy2027.pdf" \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --overwrite
```

Expected result: a small progress block ending with
`Finished[########################################]  100.0000%`.

**Wait, then check the markdown container.**

```bash
az storage blob list --container-name supply-chain-markdown \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --query "[].name" -o tsv
```

Expected result: `new_supplier_audit_fy2027.md`. On the Consumption plan the
trigger polls for new blobs, so this can take a few minutes; if the list is
empty, wait and run it again.

**Check the results container.**

```bash
az storage blob list --container-name supply-chain-results \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --query "[].name" -o tsv
```

Expected result: `new_supplier_audit_fy2027.answer.md`.

**Read the answer back.**

```bash
az storage blob download --container-name supply-chain-results \
  --name new_supplier_audit_fy2027.answer.md --file /tmp/answer.md \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --output none
open -e /tmp/answer.md
```

Expected result: TextEdit shows the question, the router's plan, the grounding
verdict and the answer.

**Watch the log stream.**

```bash
az webapp log tail --name "func-supplychain-$SUFFIX" --resource-group "$RG"
```

Expected result: lines such as `New PDF new_supplier_audit_fy2027.pdf: starting
the pipeline` followed by `Finished ...`. Stop it with Ctrl+C. The portal's
**Function app -> Monitor -> Invocations** tab shows the same runs.

Two limits worth knowing: the Consumption plan polls for new blobs, so a
trigger can be a few minutes late; and a run is stopped after 10 minutes
(`functionTimeout` in `function_app/host.json`), which a very large PDF can
exceed.

---

## 8. Trigger it by hand over HTTP

**Get the function key.** The `run` route uses `auth_level=FUNCTION`, so a key
is required.

```bash
az functionapp keys list --name "func-supplychain-$SUFFIX" --resource-group "$RG" \
  --query "functionKeys.default" -o tsv
```

Expected result: a long string. Keep it in a variable rather than on screen:

```bash
KEY=$(az functionapp keys list --name "func-supplychain-$SUFFIX" --resource-group "$RG" \
  --query "functionKeys.default" -o tsv)
```

Expected result: no output. `az functionapp function keys list --name ... --resource-group ... --function-name run_agent_manually`
shows the per-function keys if you prefer those.

**Process one blob.**

```bash
curl -sS -X POST "https://func-supplychain-$SUFFIX.azurewebsites.net/api/run?code=$KEY" \
  -H "Content-Type: application/json" \
  -d '{"blob": "new_supplier_audit_fy2027.pdf"}'
```

Expected result: the same JSON `process_blob` returns, with `"status": "ok"`.

**Ask the agent a question, on what is already indexed.**

```bash
curl -sS -X POST "https://func-supplychain-$SUFFIX.azurewebsites.net/api/run?code=$KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "How did customer OTIF change between FY2025 and FY2026?"}'
```

Expected result: JSON with `"status": "ok"` and an `"agent"` object holding
`intent`, `plan`, `answer`, `grounding_verdict` and `citations`.

Both work as `GET` too, with the values in the query string:
`.../api/run?code=$KEY&question=...`.

---

## 9. Deploy the web UI (optional)

`hosting.md` walks through the App Service plan, the web app, the sign-in
settings and Application Insights. The short version, once those exist:

```bash
RESOURCE_GROUP=$RG APP_NAME="supplychain-web-$SUFFIX" bash azure_setup/deploy-app.sh
```

Expected result: `1. Packaging`, a zip size, `2. Uploading ...`, then
`Live: https://supplychain-web-12345.azurewebsites.net`.

The zip leaves out `function_app/`, because the function app has its own
deployment script.

---

## 10. Put this guide in Azure (optional)

A private container is a convenient place to keep the documentation next to
the data.

```bash
az storage container create --name documentation \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --public-access off --output none
```

Expected result: no output. `--public-access off` keeps it private.

```bash
az storage blob upload --container-name documentation \
  --file docs/AZURE_STEP_BY_STEP.md --name AZURE_STEP_BY_STEP.md \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --overwrite
```

Expected result: a progress block ending at `100.0000%`.

---

## 11. Cost and teardown

While the resources exist you pay for Azure AI Search (Basic, per hour), the
App Service plan (B1, per hour), and per-token use of Azure OpenAI. The
function app on the Consumption plan costs almost nothing when idle.

**Delete everything.**

```bash
bash azure_setup/teardown.sh
```

Expected result: it asks `Delete resource group 'rg-supply-chain-rag' and
everything in it? Type yes to confirm:`. Type `yes`, and it prints
`Deletion started. It finishes in a few minutes -- check the Azure portal.`

The function app is inside the same resource group, so it goes too.

**Confirm it is gone.**

```bash
az group exists --name "$RG"
```

Expected result: `false`.

Azure OpenAI is soft-deleted for 48 hours, which blocks reusing the same
names. `teardown.sh` ends with the two commands that purge it immediately.

---

## 12. Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| `Please run 'az login' to setup account.` | The CLI has no session, or it expired | `az login`, then `az account show --query name -o tsv` |
| `The name ... is already taken` on create | Storage, OpenAI, Search and web app names are unique worldwide | Pick another `SUFFIX` and run the block again |
| `Quota exceeded` or `model not available in this region` | The subscription has no quota for that model there | Try `LOCATION=swedencentral` or `eastus`, or deploy a model you do have and set its name in `.env` |
| `401` or `Invalid API key` from Azure AI Search | The key is not the admin key, or it was copied short | `az search admin-key show --service-name "srch-supplychain-$SUFFIX" --resource-group "$RG" --query primaryKey -o tsv` and paste it whole (32 characters) |
| `The specified container does not exist` | The container was never created, or the name has a typo | `az storage container create --name supply-chain-docs --connection-string "$CONN" --output none` |
| `az storage blob upload` times out | A large PDF on a slow link | Add `--timeout 600`, or upload from the portal |
| The trigger never fires | Still polling, or the path setting is wrong | Wait a few minutes; check `az functionapp config appsettings list --name "func-supplychain-$SUFFIX" --resource-group "$RG" --query "[?name=='BLOB_TRIGGER_PATH'].value" -o tsv` shows `supply-chain-docs/{name}` |
| `401` on `/api/run` | No function key, or the wrong one | `az functionapp keys list --name "func-supplychain-$SUFFIX" --resource-group "$RG" --query "functionKeys.default" -o tsv` and pass it as `?code=` |
| `ModuleNotFoundError: config` in the function log | The zip was built without the project files | Re-run `RESOURCE_GROUP=$RG FUNC_NAME="func-supplychain-$SUFFIX" bash azure_setup/deploy-function.sh` |
| A question never reaches an uploaded document | `doc_type` is `uploaded`, which is not in `config.VALID_PAIRS`, so the router drops it | Expected: the chunks are indexed but the router will not plan a search for them. Ask about the five known documents, or extend the router |

When a flag is not what you expect, ask the CLI itself:

```bash
az functionapp create --help
```

Expected result: the full list of flags for that command, with a short
description of each.

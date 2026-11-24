"""
================================================================================
AZURE FUNCTION - RUN THE PIPELINE WHEN A PDF LANDS, OR WHEN YOU ASK
================================================================================

WHAT THIS FILE IS
-----------------
An Azure Function App in the PYTHON V2 PROGRAMMING MODEL: one file, one
FunctionApp object, and a decorator per function. Azure reads the decorators
and creates the triggers and routes for you -- there is no function.json.

TWO FUNCTIONS
-------------
    on_new_pdf            BLOB TRIGGER
                          fires when a file is added to the PDF container
                          (supply-chain-docs) and runs the whole pipeline on it:
                          markdown, index, agent answer

    run_agent_manually    HTTP TRIGGER, POST or GET /api/run
                          ?blob=<name>      process that one blob, like the trigger
                          ?question=<text>  just ask the agent, on what is indexed
                          A JSON body with the same keys works too.

WHY THE TRIGGER PATH IS AN APP SETTING
--------------------------------------
The container name has to be a literal inside the decorator, and a literal
cannot be changed after deployment. So the path is written as
"%BLOB_TRIGGER_PATH%" and the real value
(supply-chain-docs/{name}) lives in an app setting. Change the setting, not
the code.

WHERE THE PROJECT CODE COMES FROM
---------------------------------
When deployed, azure_setup/deploy-function.sh puts this file at the root of the
zip together with config.py, azure_clients.py, ingestion/, graph/ and the rest,
so the project code sits NEXT TO this file. Run locally with `func start`, the
project code is one folder UP. The loop below adds whichever of the two holds
config.py, so both layouts work without editing anything.

HOW TO RUN LOCALLY (optional)
-----------------------------
    cp function_app/local.settings.json.example function_app/local.settings.json
    # fill in the placeholders, then:
    cd function_app && func start

HOW TO DEPLOY
-------------
    bash azure_setup/provision-function.sh      (creates the app, then deploys)
================================================================================
"""

import json                                     # request and response bodies
import logging                                  # the function's log stream
import sys                                      # sys.path decides where the project code is found
from pathlib import Path                        # Path builds file paths

import azure.functions as func                  # the Azure Functions SDK: decorators and request/response types

HERE = Path(__file__).parent                    # this folder: function_app/
for candidate in (HERE, HERE.parent):           # deployed: next to this file. Locally: one folder up
    if (candidate / "config.py").exists():      # the folder that holds the project code
        sys.path.insert(0, str(candidate))      # make it importable, ahead of anything else
        break                                   # first match wins

import config                                   # noqa: E402  container names, the five documents
from ingestion.process_blob import ask_agent, process_blob  # noqa: E402  the pipeline this app triggers

try:                                            # monitoring is optional: telemetry.setup() does nothing
    import telemetry                            # without APPLICATIONINSIGHTS_CONNECTION_STRING
    telemetry.setup()                           # switch Application Insights on, if it is configured
except Exception as exc:                        # a missing package must not stop the functions loading
    logging.warning("Application Insights not switched on: %s", exc)

app = func.FunctionApp()                        # the one object Azure reads the decorators from


# ==============================================================================
# FUNCTION 1 - A NEW PDF IN THE CONTAINER
# ==============================================================================

@app.blob_trigger(                              # fires once per new or updated blob
    arg_name="blob",                            # the parameter name below
    path="%BLOB_TRIGGER_PATH%",                 # e.g. supply-chain-docs/{name}, from an app setting
    connection="AzureWebJobsStorage",           # the app setting holding the storage connection string
)
def on_new_pdf(blob: func.InputStream) -> None:
    """Run the whole pipeline on a PDF that has just been uploaded."""
    trigger_name = blob.name or ""              # e.g. "supply-chain-docs/new_supplier_audit_fy2027.pdf"
    prefix = f"{config.AZURE_STORAGE_CONTAINER}/"  # the container part the trigger adds to the name
    blob_name = trigger_name[len(prefix):] if trigger_name.startswith(prefix) else trigger_name  # the name inside it

    if not blob_name.lower().endswith(".pdf"):  # the markdown and answer containers are not watched, but be safe
        logging.info("Ignoring %s: not a PDF", trigger_name)
        return                                  # nothing to do

    logging.info("New PDF %s: starting the pipeline", blob_name)
    outcome = process_blob(blob_name)           # markdown, index, agent answer -- the same call the CLI makes
    logging.info("Finished %s: %s", blob_name, json.dumps(outcome, default=str))  # one line with the whole result


# ==============================================================================
# FUNCTION 2 - ASK FOR IT BY HAND
# ==============================================================================

def _request_value(req: func.HttpRequest, key: str) -> str:
    """Read one value from the query string, else from a JSON body. Empty string if it is not there."""
    value = req.params.get(key)                 # ?blob=... or ?question=...
    if value:                                   # found in the query string
        return value.strip()
    try:                                        # a JSON body is optional
        body = req.get_json()
    except ValueError:                          # no body, or not JSON
        return ""
    return str(body.get(key) or "").strip()     # the same key in the body


@app.route(                                   # an HTTP endpoint: POST or GET /api/run
    route="run",
    methods=["POST", "GET"],
    auth_level=func.AuthLevel.FUNCTION,        # a function key is required (?code=... or the x-functions-key header)
)
def run_agent_manually(req: func.HttpRequest) -> func.HttpResponse:
    """Process one blob, or ask the agent a question, and return JSON."""
    blob_name = _request_value(req, "blob")     # a blob to ingest first
    question = _request_value(req, "question")  # or a question about what is already indexed

    if blob_name:                               # the same work the blob trigger does
        outcome = process_blob(blob_name)
        status = 500 if outcome["status"] == "error" else 200  # only a total failure is an error
        return _json(outcome, status)

    if question:                                # the agent alone, on the existing index
        try:
            answer = ask_agent(question)
        except Exception as exc:                # report it as JSON rather than a stack trace
            logging.exception("agent failed for question %s", question[:80])
            return _json({"status": "error", "question": question,
                          "errors": [f"{type(exc).__name__}: {exc}"]}, 500)
        return _json({"status": "ok", "question": question, "agent": answer}, 200)

    return _json({"status": "error",
                  "errors": ["pass ?blob=<name> to process a file, or ?question=<text> to ask the agent"]}, 400)


def _json(payload: dict, status: int) -> func.HttpResponse:
    """One JSON response, with the status code the caller chose."""
    return func.HttpResponse(                   # what the HTTP trigger sends back
        json.dumps(payload, default=str),       # dates and other odd types become strings
        mimetype="application/json",
        status_code=status,
    )

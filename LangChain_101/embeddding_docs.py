from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
load_dotenv(override=True)
import os
from embedding_utils import get_documents_from_user, save_embeddings
api_key = os.getenv("OPENAI_API_KEY")

# NOTE: model + dimensions must be IDENTICAL to embedding_query.py.
# Similarity search compares a document vector to a query vector - that
# only makes sense if both were produced by the same model/size. (This
# used to be text-embedding-3-large / 50 here, which did NOT match
# embedding_query.py's text-embedding-3-small / 150 - fixed so
# similarity_search.py and rag_chat.py can compare them correctly.)
embedding = OpenAIEmbeddings(
    model = "text-embedding-3-small",
    dimensions = 150,
    api_key = api_key
)

# ============================================================
# KEVIN'S ORIGINAL SECTION (kept as-is for reference/learning).
# This is a hardcoded list of 3 sample documents about Oracle.
# Not executed anymore (see interactive section below instead) -
# uncomment the block below any time you want to go back to it.
# ============================================================
# documents = [
#     """
#     Oracle Corporation is one of the world's largest enterprise software companies,
#     founded in 1977 by Larry Ellison, Bob Miner, and Ed Oates. The company is best
#     known for its relational database management systems, which power mission-critical
#     applications for businesses across industries. Over the years, Oracle has expanded
#     its portfolio to include cloud computing, enterprise resource planning (ERP),
#     customer relationship management (CRM), and supply chain management solutions.
#     Today, Oracle serves thousands of organizations globally, helping them manage
#     data, automate processes, and improve business decision-making.
#     """,
#
#     """
#     Oracle Cloud Infrastructure (OCI) is the company's cloud computing platform,
#     designed to provide scalable, secure, and high-performance cloud services.
#     OCI offers services across computing, storage, networking, databases, analytics,
#     artificial intelligence, and machine learning. Organizations use OCI to modernize
#     legacy applications, run data-intensive workloads, and accelerate digital
#     transformation initiatives. Oracle's cloud strategy emphasizes performance,
#     security, and cost efficiency, making it a competitive alternative to other
#     major cloud providers.
#     """,
#
#     """
#     In recent years, Oracle has invested heavily in artificial intelligence and
#     autonomous technologies. Products such as the Autonomous Database automate
#     routine administrative tasks like patching, tuning, and backups, reducing
#     operational overhead for organizations. Oracle has also integrated generative
#     AI capabilities into its business applications, enabling users to automate
#     workflows, generate insights, and enhance productivity. These innovations
#     position Oracle as a key player in the rapidly evolving enterprise AI landscape.
#     """
# ]
#
# result = embedding.embed_documents(documents)
# print(f"Length of embedding vector for each document: {[len(vec) for vec in result]}")
# print(result)


# ============================================================
# ADDED SECTION (learning notes below) - interactive version.
# Goal: instead of hardcoding the documents, ask the user at
# run time for EITHER pasted text OR a file to embed.
# ============================================================
#
# How it works, step by step:
# 1. Ask the user to choose: type/paste text, or give a file path.
# 2. If "type": read multiple paragraphs from the keyboard. Since
#    a document can span several lines, we keep reading lines
#    until the user types a line that just says "END" - that is
#    our simple "stop signal". Blank lines are allowed inside a
#    document (useful for multi-paragraph text).
# 3. If "file": read the file's contents as one document. We
#    support plain text (.txt, .md, etc.) with the standard
#    library, and .pdf via pypdf if it is installed (optional,
#    so this script still runs even without pypdf).
# 4. Either way we end up with a list of one or more documents,
#    exactly like Kevin's original `documents` list above, and
#    reuse the exact same `embedding.embed_documents(...)` call.

# NOTE: the file-reading / "ask the user" helper functions that used to be
# defined here (read_pdf_text, read_excel_text, read_word_text,
# read_file_text, pick_file_with_dialog, get_documents_from_user) moved to
# embedding_utils.py - embedding_query.py needed the exact same functions,
# so keeping one shared copy avoids duplicate code to maintain in two files.

# ============================================================
# STEP 2 ADDED: persist the embeddings instead of only printing them.
# Each run used to throw the vectors away once the script ended, so the
# next script (similarity_search.py) had no way to use them without
# re-embedding (and re-paying for) the same text. Now we save them to
# doc_embeddings.json, next to this script.
# ============================================================
EMBEDDINGS_FILE = os.path.join(os.path.dirname(__file__), "doc_embeddings.json")

if __name__ == "__main__":
    documents = get_documents_from_user()
    result = embedding.embed_documents(documents)
    print(f"Number of documents embedded: {len(documents)}")
    print(f"Length of embedding vector for each document: {[len(vec) for vec in result]}")
    save_embeddings(EMBEDDINGS_FILE, documents, result)
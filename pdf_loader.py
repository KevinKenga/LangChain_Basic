import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader

# your copy of the paper (the professor's path points to his external drive)
PDF_PATH = "/Users/msp/Downloads/gpt-1paper.pdf"

# folder that holds LangChain_100/.env with the API key
BASE_DIR = Path("/Users/msp/Desktop/TTU ONE DRIVE Copy/Bootcamps/AI&ML/Sep 27 Batch HandsOn/LangChain_Basic/LangChain_100")
load_dotenv(BASE_DIR / ".env", override=True)

# create the loader object
loader = PyPDFLoader(PDF_PATH)

# create the document object
docs = loader.load()

print(f"Number of document objects created from the pdf : {len(docs)}")
print(f"Page content of the first document object : {docs[0].page_content}")

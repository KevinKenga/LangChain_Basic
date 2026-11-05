'''
Document loader
Creates document objects : page_content and metadata
'''
from langchain_community.document_loaders import PyPDFLoader

PATH = "/Volumes/Work/Oracle_26_30Oct/langchain_101/gpt-1paper.pdf"
# create a loader object 
loader = PyPDFLoader(PATH)
print("Loader object created successfully ......")

# create the document object
document_object = loader.load()

# print the document object
print("Document object created successfully ......")
print(f"Entire textual dump:  {document_object}")  # print the document object
print(f"Length of document objects being created : {len(document_object)}")  # print the length of the document object
print("="* 50)
print(f"First document object : {document_object[0].page_content}")  # print the first document object

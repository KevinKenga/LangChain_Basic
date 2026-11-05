'''
Text splitting process also called as Chunking process
Split the document objects created by the document loader into smaller chunks of text
we define the chunk size and the overlap size
Typically overlap size is set to 30%-50% of the chunk size
'''

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

PATH = "/Volumes/Work/Oracle_26_30Oct/langchain_101/gpt-1paper.pdf"
# create a loader object 
loader = PyPDFLoader(PATH)
print("Loader object created successfully ......")

# create the document object
document_objects = loader.load()

# print the first document object
print("Document object created successfully ......")
print(f"Length of document objects being created : {len(document_objects)}")  # print the length of the document object
print(f"First document object : {document_objects[0].page_content}")  

print("="* 50)
print("Chunking process started ......")

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size = 300,
    chunk_overlap = 120
)

# apply the text splitter to the document object
chunks = text_splitter.split_documents(document_objects)
print(f"Chunks created successfully ...... Total chunks : {len(chunks)}")
print("="* 50)
print(f"First chunk : {chunks[0].page_content}")  # print the first chunk
print("="* 50)
print(f"Second chunk : {chunks[1].page_content}")  # print the second
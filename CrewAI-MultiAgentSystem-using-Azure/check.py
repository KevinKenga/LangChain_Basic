from dotenv import load_dotenv
import os

# Force load the file
loaded = load_dotenv(".env")
print(f"Did .env file load? {loaded}")

# Check specific key
key = os.getenv("OPENAI_API_KEY")
if key:
    print(f"✅ Key Found: {key[:5]}...")
else:
    print(f"❌ Key Missing. Keys found in environment: {[k for k in os.environ.keys() if 'OPENAI' in k]}")
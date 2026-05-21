import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

print("Available models:")
for m in client.models.list():
    if "flash" in m.name:
        print(m.name)

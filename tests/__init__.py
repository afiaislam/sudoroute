# Tests never call a real language model, even when a .env with a real key exists:
# an empty key here wins over .env (config only fills unset variables). Gemini tests use a simulated API.
import os

os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_API_KEY"] = ""
os.environ["TS_LLM_PROVIDER"] = ""

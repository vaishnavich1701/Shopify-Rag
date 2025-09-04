# debug_env.py (place in project root)
import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

print("cwd:", Path.cwd())
# try load .env from cwd
load_dotenv()
print("MONGODB_URI after load_dotenv():", os.getenv("MONGODB_URI"))

# also try explicit .env at repo root
env_path = Path(__file__).resolve().parent / ".env"
print(".env exists at", env_path.exists(), "->", env_path)
if env_path.exists():
    print("raw .env preview:", list(dict(dotenv_values(env_path)).items())[:5])

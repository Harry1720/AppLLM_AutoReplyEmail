from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()  # load file .env

def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise Exception("SUPABASE_URL hoặc SUPABASE_SERVICE_KEY chưa set")
    return create_client(url, key)
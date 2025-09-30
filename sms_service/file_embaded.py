# file_embaded.py
# import os
# from typing import Optional, List, Dict, Tuple
# from openai import AsyncOpenAI
# import json, sqlite3, aiofiles, asyncio
# from functools import lru_cache
# import numpy as np
# from dotenv import load_dotenv

# load_dotenv()

# EMBED_MODEL = "text-embedding-3-small" 
# DATABASE_FILE = "leads.db"
# SIM_THRESHOLD = 0.80  # Lowered for better matching
# client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# _cached_file_id: Optional[str] = None
# _cached_vectors: Optional[np.ndarray] = None
# _cached_answers: Optional[List[str]] = None

# def _get_latest_file_id() -> Optional[str]:
#     """Return newest file_id from uploaded_files table (or None)."""
#     conn = sqlite3.connect(DATABASE_FILE)
#     cursor = conn.cursor()
#     cursor.execute("SELECT file_id FROM uploaded_files ORDER BY id DESC LIMIT 1")
#     row = cursor.fetchone()
#     conn.close()
#     return row[0] if row else None

# async def download_uploaded_dataset(file_id: str) -> List[Dict]:
#     # The async OpenAI client's helper returns bytes
#     file_bytes = await client.files.content(file_id)
#     lines = file_bytes.decode("utf-8").splitlines()
#     return [json.loads(line) for line in lines]

# async def build_embedding_cache(file_id: str) -> Tuple[np.ndarray, List[str]]:
#     global _cached_file_id, _cached_vectors, _cached_answers
    
#     # Return cached if already built for this file_id
#     if file_id == _cached_file_id and _cached_vectors is not None:
#         return _cached_vectors, _cached_answers
    
#     # Download and process dataset
#     dataset = await download_uploaded_dataset(file_id)
    
#     prompts = [row["prompt"] if "prompt" in row else row["user_input"]
#                for row in dataset]
#     answers = [row["completion"] if "completion" in row else row["bot_response"]
#                for row in dataset]
    
#     # batch embed to keep token-usage low (100 at a time)
#     all_vectors: List[List[float]] = []
#     for i in range(0, len(prompts), 100):
#         batch = prompts[i:i+100]
#         resp = await client.embeddings.create(model=EMBED_MODEL, input=batch)
#         all_vectors.extend([d.embedding for d in resp.data])
    
#     # Cache the results
#     _cached_file_id = file_id
#     _cached_vectors = np.array(all_vectors, dtype=np.float32)
#     _cached_answers = answers
    
#     return _cached_vectors, _cached_answers

# async def answer_from_uploaded_file(user_msg: str) -> Optional[str]:
#     file_id = _get_latest_file_id()
#     if not file_id:
#         return None

#     vectors, answers = await build_embedding_cache(file_id)

#     # embed user message
#     resp = await client.embeddings.create(model=EMBED_MODEL, input=[user_msg])
#     q_vec = np.array(resp.data[0].embedding, dtype=np.float32)

#     # cosine similarities in one vectorised op
#     sims = vectors @ q_vec / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(q_vec))
#     best_idx = int(np.argmax(sims))
    
#     print(f"[DEBUG] Best similarity: {sims[best_idx]:.3f}, Answer: {answers[best_idx][:60]}")
    
#     if sims[best_idx] >= SIM_THRESHOLD:
#         return answers[best_idx].lstrip()
#     return None


# file_embaded.py
import os
from typing import Optional, List, Dict, Tuple
from openai import AsyncOpenAI
import json, sqlite3, aiofiles, asyncio
from functools import lru_cache
import numpy as np
from dotenv import load_dotenv
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

EMBED_MODEL = "text-embedding-3-small" 
DATABASE_FILE = "../leads.db"
SIM_THRESHOLD = 0.80  # Lowered for better matching
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_cached_file_id: Optional[str] = None
_cached_vectors: Optional[np.ndarray] = None
_cached_answers: Optional[List[str]] = None

import inspect, json

async def download_uploaded_dataset(file_id: str) -> list[dict]:
    """
    Fetch the JSONL file stored on OpenAI and return it as a list of dicts.
    Works with every AsyncOpenAI version.
    """
    resp = await client.files.content(file_id)          # bytes OR response

    if isinstance(resp, (bytes, bytearray)):            # ≥ v1.3  → bytes
        raw = resp

    elif hasattr(resp, "read"):                         # v1.1 / v1.2
        # .read may be async or sync — test once
        raw = await resp.read() if inspect.iscoroutinefunction(resp.read) else resp.read()

    else:                                               # unexpected; fallback
        raise TypeError(f"Unsupported response type from files.content(): {type(resp)}")

    lines = raw.decode("utf-8").splitlines()
    return [json.loads(line) for line in lines]

def _get_latest_file_id() -> Optional[str]:
    """Return newest file_id from uploaded_files table (or None)."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM uploaded_files ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0]


async def build_embedding_cache(file_id: str) -> Tuple[np.ndarray, List[str]]:
    global _cached_file_id, _cached_vectors, _cached_answers
    
    # Return cached if already built for this file_id
    if file_id == _cached_file_id and _cached_vectors is not None:
        return _cached_vectors, _cached_answers
    
    # Download and process dataset
    dataset = await download_uploaded_dataset(file_id)
    
    prompts = [row["prompt"] if "prompt" in row else row["user_input"]
               for row in dataset]
    answers = [row["completion"] if "completion" in row else row["bot_response"]
               for row in dataset]
    
    # batch embed to keep token-usage low (100 at a time)
    all_vectors: List[List[float]] = []
    for i in range(0, len(prompts), 100):
        batch = prompts[i:i+100]
        resp = await client.embeddings.create(model=EMBED_MODEL, input=batch)
        all_vectors.extend([d.embedding for d in resp.data])
    
    # Cache the results
    _cached_file_id = file_id
    _cached_vectors = np.array(all_vectors, dtype=np.float32)
    _cached_answers = answers
    
    return _cached_vectors, _cached_answers

async def answer_from_uploaded_file(user_msg: str) -> Optional[str]:
    file_id = _get_latest_file_id()
    if not file_id:
        return None

    vectors, answers = await build_embedding_cache(file_id)

    # embed user message
    resp = await client.embeddings.create(model=EMBED_MODEL, input=[user_msg])
    q_vec = np.array(resp.data[0].embedding, dtype=np.float32)

    # cosine similarities in one vectorised op
    sims = vectors @ q_vec / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(q_vec))
    best_idx = int(np.argmax(sims))
    
    print(f"[DEBUG] Best similarity: {sims[best_idx]:.3f}, Answer: {answers[best_idx][:60]}")
    
    if sims[best_idx] >= SIM_THRESHOLD:
        return answers[best_idx].lstrip()
    return None

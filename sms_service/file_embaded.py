# file_embaded.py
import os
from typing import Optional, List, Dict, Tuple
from openai import AsyncOpenAI
import json, sqlite3, aiofiles, asyncio
from functools import lru_cache
import numpy as np
from dotenv import load_dotenv

load_dotenv()

EMBED_MODEL = "text-embedding-3-small" 
DATABASE_FILE = "leads.db"
SIM_THRESHOLD = 0.80  # Lowered for better matching
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_cached_file_id: Optional[str] = None
_cached_vectors: Optional[np.ndarray] = None
_cached_answers: Optional[List[str]] = None

def _get_latest_file_id(database_file:str = DATABASE_FILE) -> Optional[str]:
    """Return newest file_id from uploaded_files table (or None)."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM uploaded_files ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None



# async def download_uploaded_dataset(file_id: str) -> List[Dict]:
#     print('Downloading dataset for file_id:', file_id)
#     # The async OpenAI client's helper returns bytes
#     file_bytes = await client.files.content(file_id)
#     print('\n\n\n\nccfile bytes---->>', file_bytes)  # print first 100 bytes for debugging
#     lines = file_bytes.decode("utf-8").splitlines()
#     return [json.loads(line) for line in lines]

async def download_uploaded_dataset(file_id: str) -> List[Dict]:
    print('Downloading dataset for file_id:', file_id)

    # Get binary content wrapper
    response = await client.files.content(file_id)

    # Read bytes from it (synchronously)
    file_bytes = response.read()
    print("\n\nFile bytes type:", type(file_bytes))
    print("First 200 chars:", file_bytes[:200])

    # Decode and parse JSON or JSONL
    try:
        lines = file_bytes.decode("utf-8").splitlines()
        return [json.loads(line) for line in lines]
    except Exception:
        return json.loads(file_bytes.decode("utf-8"))

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

async def answer_from_uploaded_file(user_msg: str,database_file:str = DATABASE_FILE) -> Optional[str]:
    file_id = _get_latest_file_id(database_file)
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









# # file_embaded.py
# import os
# from typing import Optional, List, Dict, Tuple
# from openai import AsyncOpenAI
# import json, sqlite3, aiofiles, asyncio
# from functools import lru_cache
# import numpy as np
# from dotenv import load_dotenv
# import sys
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# load_dotenv()

# EMBED_MODEL = "text-embedding-3-small" 
# # DATABASE_FILE = "../leads.db"
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# print(">>>>>>>BASE_DIR>>>>>>>",BASE_DIR)
# DATABASE_FILE = os.path.join(BASE_DIR, "../leads.db")
# DATABASE_FILE = os.path.abspath(DATABASE_FILE)
# SIM_THRESHOLD = 0.80  # Lowered for better matching
# client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# _cached_file_id: Optional[str] = None
# _cached_vectors: Optional[np.ndarray] = None
# _cached_answers: Optional[List[str]] = None

# import inspect, json

# async def download_uploaded_dataset(file_id: str) -> list[dict]:
#     """
#     Fetch the JSONL file stored on OpenAI and return it as a list of dicts.
#     Works with every AsyncOpenAI version.
#     """
#     resp = await client.files.content(file_id)          # bytes OR response

#     if isinstance(resp, (bytes, bytearray)):            # ≥ v1.3  → bytes
#         raw = resp

#     elif hasattr(resp, "read"):                         # v1.1 / v1.2
#         # .read may be async or sync — test once
#         raw = await resp.read() if inspect.iscoroutinefunction(resp.read) else resp.read()

#     else:                                               # unexpected; fallback
#         raise TypeError(f"Unsupported response type from files.content(): {type(resp)}")

#     lines = raw.decode("utf-8").splitlines()
#     return [json.loads(line) for line in lines]

# def _get_latest_file_id(database_file:str = DATABASE_FILE) -> Optional[str]:
#     """Return newest file_id from uploaded_files table (or None)."""
#     conn = sqlite3.connect(database_file)
#     cursor = conn.cursor()
#     cursor.execute("SELECT file_id FROM uploaded_files ORDER BY id DESC LIMIT 1")
#     row = cursor.fetchone()
#     conn.close()
#     return row[0]


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

# async def answer_from_uploaded_file(user_msg: str, database_file:str = DATABASE_FILE) -> Optional[str]:
#     file_id = _get_latest_file_id(database_file)
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



# # file_embaded.py
# import os
# import json
# import sqlite3
# import asyncio
# from typing import Optional, List, Tuple
# import numpy as np
# from dotenv import load_dotenv
# from openai import AsyncOpenAI
# from langchain_community.vectorstores import FAISS
# from langchain_openai import OpenAIEmbeddings


# load_dotenv()

# # ================= Configuration =================
# EMBED_MODEL = "text-embedding-3-small"
# SIM_THRESHOLD = 0.80  # similarity threshold for answer
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DATABASE_FILE = os.path.abspath(os.path.join(BASE_DIR, "../leads.db"))



# # Initialize OpenAI client
# client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# # Cached embeddings and answers to avoid repeated embedding calls
# _cached_vectors: Optional[np.ndarray] = None
# _cached_answers: Optional[List[str]] = None

# # ================= Helper Functions =================
# def load_dataset_from_db(database_file: str = DATABASE_FILE) -> List[dict]:
#     """
#     Load the latest dataset from the SQLite DB.
#     Assumes the 'uploaded_files' table has a 'data' column storing JSON array.
#     """
#     conn = sqlite3.connect(database_file)
#     cursor = conn.cursor()
#     cursor.execute("SELECT data FROM uploaded_files ORDER BY id DESC LIMIT 1")
#     row = cursor.fetchone()
#     conn.close()
#     if not row:
#         return []
#     try:
#         dataset = json.loads(row[0])
#     except json.JSONDecodeError:
#         return []
#     return dataset

# # ================= Embedding Cache =================
# async def build_embedding_cache() -> Tuple[np.ndarray, List[str]]:
#     """
#     Build embeddings for all prompts in the dataset and cache them.
#     Returns:
#         - vectors: np.ndarray of shape (num_prompts, embedding_dim)
#         - answers: List of corresponding answers
#     """
#     global _cached_vectors, _cached_answers

#     dataset = load_dataset_from_db()
#     if not dataset:
#         return np.array([]), []

#     prompts = [row.get("prompt") or row.get("user_input") for row in dataset]
#     answers = [row.get("completion") or row.get("bot_response") for row in dataset]

#     all_vectors: List[List[float]] = []
#     batch_size = 100  # batch embedding to save tokens

#     for i in range(0, len(prompts), batch_size):
#         batch = prompts[i:i + batch_size]
#         resp = await client.embeddings.create(model=EMBED_MODEL, input=batch)
#         all_vectors.extend([d.embedding for d in resp.data])

#     _cached_vectors = np.array(all_vectors, dtype=np.float32)
#     _cached_answers = answers

#     return _cached_vectors, _cached_answers

# # ================= Answer Retrieval =================
# # async def answer_from_uploaded_file(user_msg: str,db) -> Optional[str]:
# #     """
# #     Find the best matching answer from the dataset using cosine similarity.
# #     """
# #     if _cached_vectors is None or _cached_answers is None:
# #         vectors, answers = await build_embedding_cache()
# #     else:
# #         vectors, answers = _cached_vectors, _cached_answers

# #     if vectors.size == 0:
# #         return None

# #     # Embed user message
# #     resp = await client.embeddings.create(model=EMBED_MODEL, input=[user_msg])
# #     q_vec = np.array(resp.data[0].embedding, dtype=np.float32)

# #     # Compute cosine similarity
# #     sims = vectors @ q_vec / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(q_vec))
# #     best_idx = int(np.argmax(sims))

# #     print(f"[DEBUG] Best similarity: {sims[best_idx]:.3f}, Answer: {answers[best_idx][:60]}")

# #     if sims[best_idx] >= SIM_THRESHOLD:
# #         return answers[best_idx].lstrip()
# #     return None

# #  load the  fiss index and retrive the answer
# async def answer_from_uploaded_file(user_msg: str, db) -> Optional[str]:
#     """
#     load the faiss index and retrive the answer
#     """

#     embeddings = OpenAIEmbeddings(
#             model="text-embedding-3-small",
#             dimensions=1024,
#             api_key=os.getenv("OPENAI_API_KEY")
#         )
#     faiss_local_index = "faissIndex"
#     print('user msg--->>>', user_msg)


#     index_path="app_data\\faiss"

#     if not os.path.exists(index_path):
#         return None

    
#     vector_store = FAISS.load_local(index_path, embeddings, index_name=faiss_local_index,allow_dangerous_deserialization=True)
#     print('vector-->>>',vector_store)
#     docs = vector_store.similarity_search(user_msg, k=1)
#     print('docs-->>>', docs)
#     return docs[0].page_content.split('Answer:')[-1] if docs else None
    



# ================= Example Usage =================
# Uncomment to test standalone
# async def test():
#     answer = await answer_from_uploaded_file("Hello, how can I contact support?")
#     print(answer)
# asyncio.run(test())


import os
import json
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from utils.loggers import log_message
from dotenv import load_dotenv

load_dotenv()


class VectorDBService:
    """
    Prepare, chunk, embed, and store dataset in FAISS vector database.
    """

    def __init__(self):
        # Initialize OpenAI embeddings
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            dimensions=1024,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.faiss_local_path = "app_data/faiss"
        self.faiss_local_index = "faissIndex"
        self.vectorstore = None  # initialize empty

    def prepare_documents(self, data: list):
        """Convert dataset JSON into LangChain Documents."""
        log_message("Preparing dataset records into Documents...")
        documents = [
            Document(
                page_content=f"Question: {d.get('user_input', '')}\nAnswer: {d.get('bot_response', '')}",
                metadata={"dataset_version": d.get("version", "unknown")}
            )
            for d in data
        ]
        log_message("Documents prepared successfully.")
        return documents

    def split_documents(self, documents, chunk_size=500, chunk_overlap=75):
        """Split documents into chunks for efficient embeddings."""
        log_message("Splitting documents into chunks...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". "],
            keep_separator=False
        )
        chunks = text_splitter.split_documents(documents)
        log_message(f"Documents split into {len(chunks)} chunks.")
        return chunks

    def save_vector_db(self, documents: list):
        """Save FAISS vector DB locally."""
        log_message("Creating FAISS vector database...")

        chunks = self.split_documents(documents)

        # Optional: log chunks
        os.makedirs("app_data/logs", exist_ok=True)
        with open("app_data/logs/chunks.json", "w", encoding="utf-8") as f:
            json.dump([c.page_content for c in chunks], f, indent=4, ensure_ascii=False)

        vectorstore = FAISS.from_documents(chunks, self.embeddings)
        os.makedirs(self.faiss_local_path, exist_ok=True)
        vectorstore.save_local(
            folder_path=self.faiss_local_path,
            index_name=self.faiss_local_index
        )
        log_message("FAISS database saved successfully.")
        self.vectorstore = vectorstore

    def load_db(self, data: list = None):
        """Load FAISS DB, automatically create if missing."""
        if not os.path.exists(self.faiss_local_path) or not os.listdir(self.faiss_local_path):
            if data is None:
                raise ValueError("FAISS DB not found. Provide `data` to create it first.")
            log_message("FAISS DB missing. Creating new DB...")
            documents = self.prepare_documents(data)
            self.save_vector_db(documents)

        log_message("Loading FAISS vector database...")
        self.vectorstore = FAISS.load_local(
            folder_path=self.faiss_local_path,
            index_name=self.faiss_local_index,
            embeddings=self.embeddings,
            allow_dangerous_deserialization=True
        )
        log_message("FAISS DB loaded successfully.")

    def search_from_db(self, query: str, k: int = 5, data: list = None):
        """Perform semantic search from FAISS DB. Auto-create/load DB if missing."""
        if self.vectorstore is None:
            self.load_db(data=data)

        results = self.vectorstore.similarity_search(query, k=k)
        return [{"page_content": res.page_content, "metadata": res.metadata} for res in results]

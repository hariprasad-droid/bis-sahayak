"""
Ingest scraped BIS documents into Supabase pgvector.
Uses Hugging Face Inference API for free embeddings (nomic-ai/nomic-embed-text-v1.5, 768 dims).
"""
import sys, io, os, json, re, time
if isinstance(sys.stdout, io.TextIOWrapper) and sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
from dotenv import load_dotenv
import requests
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

# Hugging Face Inference API (free, no key needed for public models)
HF_EMBED_URL = "https://api-inference.huggingface.co/pipeline/feature-extraction/nomic-ai/nomic-embed-text-v1.5"

DATA_DIR = BASE_DIR / "data" / "raw"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CATEGORY_PATTERNS = [
    (r'hallmark|huid|ahc|jewel|gold', 'Hallmarking'),
    (r'product.certif|scheme.i|isi.mark|conformity|licence', 'Product Certification'),
    (r'qco|quality.control.order|gazette', 'Quality Control Orders'),
    (r'crs|compulsory.registration|electronics|meity', 'CRS / Electronics'),
    (r'fmcs|foreign.manufactur', 'FMCS'),
    (r'water|drinking|is.14543|is.10500', 'Drinking Water'),
    (r'fee|marking.fee|cost|charge', 'Fees & Charges'),
    (r'bis.act|regulation|amendment', 'BIS Act & Regulations'),
    (r'faq|frequently', 'FAQs'),
    (r'consumer|complaint', 'Consumer Affairs'),
]

def detect_category(filename):
    name_lower = filename.lower()
    for pattern, category in CATEGORY_PATTERNS:
        if re.search(pattern, name_lower):
            return category
    return "General"

_embedding_model = None
def get_embedding_hf(text):
    """Get 768-dim embedding using local sentence-transformers."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            print("Loading local embedding model...", end=" ", flush=True)
            _embedding_model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
            print("Done.")
    
    try:
        emb = _embedding_model.encode(text[:2000])
        return emb.tolist()
    except Exception as e:
        print(f"    Embedding error: {e}")
        return None

def chunk_text(text, chunk_size=600, overlap=100):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks

def ingest_file(filepath, category=None):
    name = filepath.name
    if category is None:
        category = detect_category(name)
    
    print(f"\n{'='*50}")
    print(f"Processing: {name} [{category}]")
    
    try:
        if filepath.suffix in ('.html', '.htm'):
            from bs4 import BeautifulSoup
            raw = filepath.read_text(encoding='utf-8', errors='ignore')
            soup = BeautifulSoup(raw, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            text = soup.get_text(separator='\n', strip=True)
        else:
            text = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        print(f"  Read error: {e}")
        return 0
    
    if len(text.strip()) < 50:
        print(f"  Too short, skipping")
        return 0
    
    chunks = chunk_text(text)
    print(f"  {len(chunks)} chunks to embed")
    
    inserted = 0
    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i+1}/{len(chunks)}...", end=" ", flush=True)
        
        embedding = get_embedding_hf(chunk)
        if embedding is None:
            print("FAILED")
            continue
        
        # Ensure 768 dimensions
        if len(embedding) != 768:
            print(f"Wrong dims ({len(embedding)}), padding/truncating")
            if len(embedding) > 768:
                embedding = embedding[:768]
            else:
                embedding = embedding + [0.0] * (768 - len(embedding))
        
        meta = {
            "source": str(filepath.relative_to(BASE_DIR)),
            "title": name.replace('.txt', '').replace('.html', '').replace('.htm', '').replace('.pdf', '').replace('_', ' ').replace('-', ' ').title(),
            "category": category,
            "file_type": filepath.suffix.lstrip('.'),
            "chunk_index": i,
        }
        
        try:
            supabase.table("documents").insert({
                "content": chunk,
                "metadata": meta,
                "embedding": embedding
            }).execute()
            inserted += 1
            print("OK")
        except Exception as e:
            print(f"INSERT ERROR: {e}")
        
        time.sleep(0.5)  # Rate limiting
    
    print(f"  => Inserted {inserted}/{len(chunks)} chunks")
    return inserted

def main():
    total = 0
    
    # 1. Text files
    for f in sorted(DATA_DIR.glob("*.txt")):
        total += ingest_file(f)
    
    # 2. HTML files 
    html_dir = DATA_DIR / "html"
    if html_dir.exists():
        html_files = sorted(list(html_dir.glob("*.html")) + list(html_dir.glob("*.htm")))
        for f in html_files:
            total += ingest_file(f)
    
    # 3. PDF files
    pdf_dir = DATA_DIR / "pdf"
    if pdf_dir.exists():
        for f in sorted(pdf_dir.glob("*.pdf")):
            total += ingest_file(f)
    
    print(f"\n{'='*50}")
    print(f"DONE! Total chunks inserted: {total}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()

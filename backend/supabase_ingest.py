"""
Ingest scraped BIS documents into Supabase pgvector using Ollama Cloud embeddings.
"""
import sys, io, os, json, re, hashlib, time
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
OLLAMA_CLOUD_URL = os.environ["OLLAMA_CLOUD_URL"].replace("/chat/completions", "/embeddings")
OLLAMA_CLOUD_KEY = os.environ["OLLAMA_CLOUD_API_KEY"]

DATA_DIR = BASE_DIR / "data" / "raw"
SOURCES_FILE = BASE_DIR / "sources.json"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Category detection
CATEGORY_PATTERNS = [
    (r'hallmark|huid|ahc|jewel|gold', 'Hallmarking'),
    (r'product.certif|scheme.i|isi.mark|conformity|licence', 'Product Certification'),
    (r'qco|quality.control.order|gazette', 'Quality Control Orders'),
    (r'crs|compulsory.registration|electronics|meity', 'CRS / Electronics'),
    (r'fmcs|foreign.manufactur', 'FMCS'),
    (r'water|drinking|is.14543|is.10500', 'Drinking Water'),
    (r'steel|iron|ferr', 'Steel & Iron'),
    (r'chemical|acid|polymer|plastic', 'Chemicals & Polymers'),
    (r'textile|cotton|yarn', 'Textiles'),
    (r'food|fssai|edible', 'Food Safety'),
    (r'solar|renewable|mnre', 'Solar & Renewable Energy'),
    (r'electrical|appliance|fan', 'Electrical Appliances'),
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

def get_embedding(text):
    """Get embedding from Ollama Cloud API."""
    headers = {
        "Authorization": f"Bearer {OLLAMA_CLOUD_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "nomic-embed-text",
        "input": text[:8000]  # Truncate very long texts
    }
    
    for attempt in range(3):
        try:
            response = requests.post(OLLAMA_CLOUD_URL, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                return response.json()["data"][0]["embedding"]
            elif response.status_code == 429:
                print(f"  Rate limited, waiting {5 * (attempt+1)}s...")
                time.sleep(5 * (attempt + 1))
            else:
                print(f"  Embedding error {response.status_code}: {response.text[:200]}")
                return None
        except Exception as e:
            print(f"  Embedding request error: {e}")
            time.sleep(2)
    return None

def chunk_text(text, chunk_size=800, overlap=150):
    """Split text into overlapping chunks."""
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
    """Ingest a single file into Supabase."""
    name = filepath.name
    if category is None:
        category = detect_category(name)
    
    print(f"\n📄 Processing: {name} [{category}]")
    
    # Read file
    try:
        if filepath.suffix == '.txt':
            text = filepath.read_text(encoding='utf-8', errors='ignore')
        elif filepath.suffix in ('.html', '.htm'):
            from bs4 import BeautifulSoup
            raw = filepath.read_text(encoding='utf-8', errors='ignore')
            soup = BeautifulSoup(raw, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            text = soup.get_text(separator='\n', strip=True)
        elif filepath.suffix == '.pdf':
            try:
                import fitz
                doc = fitz.open(str(filepath))
                text = '\n'.join(page.get_text() for page in doc)
                doc.close()
            except:
                print(f"  ⚠ Could not read PDF: {name}")
                return 0
        else:
            text = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        print(f"  ⚠ Read error: {e}")
        return 0
    
    if len(text.strip()) < 50:
        print(f"  ⚠ Too short, skipping")
        return 0
    
    # Chunk
    chunks = chunk_text(text)
    print(f"  → {len(chunks)} chunks")
    
    inserted = 0
    for i, chunk in enumerate(chunks):
        embedding = get_embedding(chunk)
        if embedding is None:
            print(f"  ⚠ Embedding failed for chunk {i+1}")
            continue
        
        meta = {
            "source": str(filepath.relative_to(BASE_DIR)),
            "title": name.replace('.txt', '').replace('.html', '').replace('.pdf', '').replace('_', ' ').title(),
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
        except Exception as e:
            print(f"  ⚠ Insert error chunk {i+1}: {e}")
        
        # Rate limiting
        time.sleep(0.3)
    
    print(f"  ✅ Inserted {inserted}/{len(chunks)} chunks")
    return inserted

def main():
    total = 0
    
    # 1. Ingest text files in data/raw
    for txt_file in sorted(DATA_DIR.glob("*.txt")):
        total += ingest_file(txt_file)
    
    # 2. Ingest HTML files
    html_dir = DATA_DIR / "html"
    if html_dir.exists():
        for html_file in sorted(html_dir.glob("*.html"))[:50]:  # Limit to first 50
            total += ingest_file(html_file)
        for html_file in sorted(html_dir.glob("*.htm"))[:50]:
            total += ingest_file(html_file)
    
    # 3. Ingest PDF files
    pdf_dir = DATA_DIR / "pdf"
    if pdf_dir.exists():
        for pdf_file in sorted(pdf_dir.glob("*.pdf"))[:30]:  # Limit to first 30
            total += ingest_file(pdf_file)
    
    print(f"\n{'='*50}")
    print(f"🎉 DONE! Total chunks inserted: {total}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()

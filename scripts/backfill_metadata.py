import sys
import logging
import argparse
import os
from pathlib import Path
from tqdm import tqdm

# Ensure src module is accessible
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
except ImportError:
    print("chromadb not installed")
    sys.exit(1)

from src.core.settings import load_settings
from src.libs.llm.llm_factory import LLMFactory
from src.ingestion.transform.metadata_enricher import MetadataEnricher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_backfill(batch_size=50, force=False):
    """
    Scan existing Chunks in ChromaDB and run them through LLM to extract structural tags.
    Updates the records in-place without touching the embeddings.
    """
    logger.info("Loading settings and initializing Metadata Enricher...")
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=project_root / ".env", override=True)
    settings = load_settings(project_root / "config" / "settings.yaml")
    
    actual_key = os.environ.get('DASHSCOPE_API_KEY')
    if actual_key:
        os.environ['OPENAI_API_KEY'] = actual_key
        logger.info("Successfully injected actual_key into OPENAI_API_KEY environment variable")
    
    enricher = MetadataEnricher(settings)
    
    # 彻底绕开 LLMFactory 与 dataclass frozen 的嵌套坑，手动打桩注入底层实例
    from src.libs.llm.openai_llm import OpenAILLM
    direct_llm = OpenAILLM(
        settings=settings, 
        api_key=actual_key, 
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    enricher._llm = direct_llm
    enricher.use_llm = True
    
    if not enricher.llm:
        logger.error("Failed to initialize LLM. Please check settings.")
        return

    persist_dir = project_root / getattr(settings.vector_store, 'persist_directory', 'data/db/chroma')
    collection_name = getattr(settings.vector_store, 'collection_name', 'knowledge_hub')
    
    logger.info(f"Connecting to ChromaDB at {persist_dir}, Collection: {collection_name}")
    client = chromadb.PersistentClient(
        path=str(persist_dir),
        settings=ChromaSettings(
            anonymized_telemetry=False,
            allow_reset=True,
            is_persistent=True,
        )
    )
    
    collection = client.get_or_create_collection(name=collection_name)
    count = collection.count()
    if count == 0:
        logger.info("ChromaDB collection is empty. Nothing to backfill.")
        return
        
    logger.info(f"Found {count} records in ChromaDB. Starting backfill (Batch size: {batch_size})...")
    
    processed_count = 0
    updated_count = 0
    
    # Process in pages
    for offset in range(0, count, batch_size):
        logger.info(f"Fetching batch offset {offset}...")
        batch = collection.get(limit=batch_size, offset=offset, include=["documents", "metadatas"])
        
        ids = batch['ids']
        documents = batch['documents']
        metadatas = batch['metadatas']
        
        updated_metadatas = []
        should_update_ids = []
        
        for i, text in enumerate(documents):
            meta = metadatas[i] or {}
            
            # Skip if already contains 'category' and 'project' unless force is True
            if not force and 'category' in meta and 'project' in meta:
                processed_count += 1
                continue
                
            logger.debug(f"Processing chunk ID: {ids[i]}")
            
            # We call the specific LLM method
            llm_result = enricher._llm_enrich(text)
            
            if llm_result:
                # Store structural fields
                meta['category'] = llm_result.get('category', '通用文档')
                meta['project'] = llm_result.get('project', 'None')
                
                # ChromaDB requires primitive types, tags should be comma-separated string
                if 'tags' in llm_result and isinstance(llm_result['tags'], list):
                    meta['tags'] = ",".join(llm_result['tags'])
            else: # fallback
                meta['category'] = '通用文档'
                meta['project'] = 'None'
                
            updated_metadatas.append(meta)
            should_update_ids.append(ids[i])
            processed_count += 1
            
        if should_update_ids:
            logger.info(f"Writing {len(should_update_ids)} updated records to ChromaDB...")
            collection.update(
                ids=should_update_ids,
                metadatas=updated_metadatas
            )
            updated_count += len(should_update_ids)
            
    logger.info(f"Backfill Complete! Processed {processed_count} chunks, Updated {updated_count} chunks.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill structural metadata using LLM against existing ChromaDB")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for retrieving from ChromaDB")
    parser.add_argument("--force", action="store_true", help="Force re-processing even if tags exist")
    args = parser.parse_args()
    
    run_backfill(batch_size=args.batch_size, force=args.force)

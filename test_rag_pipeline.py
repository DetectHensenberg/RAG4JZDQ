import asyncio
import os
from src.core.settings import load_settings
from src.mcp_server.tools.query_knowledge_hub import get_tool_instance

async def main():
    print("Loading settings...")
    settings = load_settings()
    
    # Debug: Check settings
    print(f"Rerank Enabled: {settings.rerank.enabled}")
    if hasattr(settings.retrieval, 'query_rewrite'):
        print(f"Query Rewrite Enabled: {settings.retrieval.query_rewrite}")
    else:
        print("Settings does not have query_rewrite attr!")

    print("Initializing QueryKnowledgeHubTool...")
    tool = get_tool_instance(settings)
    
    print("\nExecuting search for '多查询扩展优化'...")
    try:
        response = await tool.execute(
            query="什么是多查询扩展优化",
            top_k=3,
        )
        print("\n--- Search Results ---")
        if response.is_empty:
            print("No results found.")
        else:
            print(f"Content preview: {response.content[:200]}...")
            print(f"\nCitations ({len(response.citations)}):")
            for i, c in enumerate(response.citations):
                print(f"[{i+1}] {c.get('source')} (Score: {c.get('score', 'N/A')})")
    except Exception as e:
        print(f"Error executing search: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    # Load .env file for API keys if needed
    try:
        from dotenv import load_dotenv
        load_dotenv("d:/WorkSpace/project/个人项目/RAG/.env")
    except:
        pass
    
    # run
    asyncio.run(main())

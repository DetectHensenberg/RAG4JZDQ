"""Test script for bid document writer functionality."""

import asyncio
import sys
sys.path.insert(0, '.')

from src.bid.clause_extractor import extract_clauses
from src.bid.outline_generator import generate_outline, generate_default_outline
from src.libs.llm import LLMFactory
from src.core.settings import load_settings


async def test():
    # Read PDF content
    import fitz
    pdf_path = r'D:\WorkSpace\project\个人项目\RAG\tests\docs\五个项目\TB20251210贵州省自然灾害应急能力提升工程 预警指挥项目 (森林防火重点区配备视频监控设备) （三次）\招标文件\招标文件.pdf'
    doc = fitz.open(pdf_path)
    content = ''.join([p.get_text() for p in doc])
    doc.close()
    print(f'PDF content: {len(content)} chars')
    
    # Extract clauses
    settings = load_settings()
    llm = LLMFactory.create(settings)
    print('Extracting clauses...')
    clauses = await extract_clauses(content, llm)
    print(f'Extracted {len(clauses)} clauses:')
    for c in clauses[:10]:
        print(f"  - {c.get('id')}: {c.get('title')} ({c.get('category')})")
    
    if clauses:
        # Generate outline
        print('\nGenerating outline...')
        outline = await generate_outline(clauses, llm)
        print(f'Generated {len(outline)} outline items:')
        for item in outline[:10]:
            indent = '  ' * item.get('level', 1)
            print(f"{indent}{item.get('id')} {item.get('title')}")
    
    return clauses


if __name__ == '__main__':
    asyncio.run(test())

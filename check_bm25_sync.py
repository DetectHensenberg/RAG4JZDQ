"""检查 BM25 索引和 ChromaDB 同步问题"""
import sqlite3
import os

# 检查 BM25 索引
bm25_dir = r'D:\WorkSpace\project\个人项目\RAG\data\db\bm25\default'
print('=== BM25 索引文件 ===')
if os.path.exists(bm25_dir):
    for f in os.listdir(bm25_dir):
        fpath = os.path.join(bm25_dir, f)
        print(f'  {f}: {os.path.getsize(fpath)} bytes')
else:
    print('  目录不存在')

# 检查 BM25 表结构
bm25_path = os.path.join(bm25_dir, 'bm25_index.db')
if os.path.exists(bm25_path):
    conn = sqlite3.connect(bm25_path)
    cursor = conn.cursor()
    
    print('\n=== BM25 表结构 ===')
    tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
    for t in tables:
        print(f'  {t[0]}')
    
    # 检查文档数
    if tables:
        tname = tables[0][0]
        count = cursor.execute(f'SELECT COUNT(*) FROM {tname};').fetchone()
        print(f'\n=== BM25 文档数: {count[0]} ===')
        
        # 样本 chunk_id
        samples = cursor.execute(f'SELECT chunk_id FROM {tname} LIMIT 5;').fetchall()
        print('\n=== 样本 chunk_id ===')
        for s in samples:
            print(f'  {s[0]}')
    
    conn.close()

# 检查 ChromaDB embedding 数量
chroma_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma.sqlite3'
if os.path.exists(chroma_path):
    conn = sqlite3.connect(chroma_path)
    cursor = conn.cursor()
    
    count = cursor.execute('SELECT COUNT(*) FROM embeddings;').fetchone()
    print(f'\n=== ChromaDB embeddings: {count[0]} ===')
    
    # 样本 embedding_id
    samples = cursor.execute('SELECT embedding_id FROM embeddings LIMIT 5;').fetchall()
    print('\n=== 样本 embedding_id ===')
    for s in samples:
        print(f'  {s[0]}')
    
    conn.close()

print('\n=== 分析 ===')
print('BM25 和 ChromaDB 的 ID 格式需要匹配')
print('SparseRetriever 警告表示 BM25 索引中的 chunk_id 在 ChromaDB 找不到')

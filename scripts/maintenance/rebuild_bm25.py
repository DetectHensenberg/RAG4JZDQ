"""重建 BM25 索引，与 ChromaDB 同步"""
import json
import sqlite3
import os
import shutil
from pathlib import Path

# 路径配置
chroma_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma.sqlite3'
bm25_dir = r'D:\WorkSpace\project\个人项目\RAG\data\db\bm25\default'
bm25_json = os.path.join(bm25_dir, 'default_bm25.json')

print('=== 1. 从 ChromaDB 读取数据 ===')
conn = sqlite3.connect(chroma_path)
cursor = conn.cursor()

# 获取所有 embedding_id 和对应的 text
print('  读取 embeddings...')
embeddings = cursor.execute('''
    SELECT e.embedding_id, em.string_value 
    FROM embeddings e
    JOIN embedding_metadata em ON e.id = em.id
    WHERE em.key = 'text' AND em.string_value IS NOT NULL
''').fetchall()

print(f'  找到 {len(embeddings)} 条记录')

conn.close()

print('\n=== 2. 构建 BM25 文档列表 ===')
documents = []
for emb_id, text in embeddings:
    if text:
        documents.append({
            'chunk_id': emb_id,
            'text': text,
            'metadata': {}  # 可以添加其他元数据
        })

print(f'  文档数: {len(documents)}')

print('\n=== 3. 备份旧索引 ===')
if os.path.exists(bm25_json):
    backup_path = bm25_json + '.backup'
    shutil.copy(bm25_json, backup_path)
    print(f'  已备份到: {backup_path}')

print('\n=== 4. 写入新索引 ===')
# BM25 索引格式：文档列表
with open(bm25_json, 'w', encoding='utf-8') as f:
    json.dump(documents, f, ensure_ascii=False)

print(f'  写入完成: {os.path.getsize(bm25_json)} bytes')

print('\n=== 5. 验证 ===')
with open(bm25_json, 'r', encoding='utf-8') as f:
    loaded = json.load(f)
    print(f'  加载文档数: {len(loaded)}')
    if loaded:
        print(f'  样本 chunk_id: {loaded[0]["chunk_id"]}')

print('\n=== 完成 ===')
print('BM25 索引已重建，重启 Dashboard 后生效')

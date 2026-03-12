"""检查 ChromaDB 向量存储结构"""
import sqlite3
import os

db_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma_backup2.sqlite3'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查所有表
print('=== 所有表 ===')
tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
for t in tables:
    print(f'  {t[0]}')

# 检查 embeddings 表结构
print('\n=== embeddings 表结构 ===')
cols = cursor.execute('PRAGMA table_info(embeddings);').fetchall()
for col in cols:
    print(f'  {col[1]}: {col[2]}')

# 检查是否有向量数据
print('\n=== 检查向量存储位置 ===')

# ChromaDB 1.x 可能在不同位置存储向量
try:
    # 检查 embedding_metadata 是否有 vector 键
    count = cursor.execute("SELECT COUNT(*) FROM embedding_metadata WHERE key='vector';").fetchone()
    print(f'  embedding_metadata.vector: {count[0]} 条')
except Exception as e:
    print(f'  embedding_metadata.vector: Error - {e}')

# 检查是否有 embeddings_blob 或类似表
for table in tables:
    tname = table[0]
    if 'vector' in tname.lower() or 'embedding' in tname.lower():
        try:
            count = cursor.execute(f'SELECT COUNT(*) FROM {tname};').fetchone()
            print(f'  {tname}: {count[0]} 条')
        except:
            pass

# 检查 segment 目录
print('\n=== Segment 目录 ===')
chroma_dir = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma'
for item in os.listdir(chroma_dir):
    item_path = os.path.join(chroma_dir, item)
    if os.path.isdir(item_path) and item not in ['.', '..']:
        print(f'  目录: {item}')
        files = os.listdir(item_path) if os.path.isdir(item_path) else []
        for f in files:
            fpath = os.path.join(item_path, f)
            size = os.path.getsize(fpath) if os.path.isfile(fpath) else 0
            print(f'    {f}: {size} bytes')

conn.close()

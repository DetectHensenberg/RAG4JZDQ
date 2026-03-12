"""修复 ChromaDB compaction 错误"""
import sqlite3
import os
import shutil

db_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma.sqlite3'
chroma_dir = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma'

# 1. 清空 embeddings_queue（待处理队列）
print('=== 1. 清空 embeddings_queue ===')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

count = cursor.execute('SELECT COUNT(*) FROM embeddings_queue;').fetchone()
print(f'  待处理记录: {count[0]}')

cursor.execute('DELETE FROM embeddings_queue;')
conn.commit()
print('  已清空 embeddings_queue')

# 2. 删除空的 HNSW segment 目录
print('\n=== 2. 删除空 segment 目录 ===')
segment_dir = os.path.join(chroma_dir, '1929a1fc-daa5-4e78-8d55-5e651c26f4a0')
if os.path.exists(segment_dir):
    # 检查是否为空
    files = os.listdir(segment_dir)
    if not files:
        os.rmdir(segment_dir)
        print(f'  已删除空目录: {segment_dir}')
    else:
        print(f'  目录非空，跳过: {files}')
else:
    print('  目录不存在')

# 3. 删除 segments 表中的记录（让 ChromaDB 重建）
print('\n=== 3. 清理 segments 表 ===')
rows = cursor.execute('SELECT * FROM segments;').fetchall()
for row in rows:
    print(f'  Segment: {row}')

# 删除 VECTOR segment 记录，保留 METADATA
cursor.execute("DELETE FROM segments WHERE type='VECTOR';")
conn.commit()
print('  已删除 VECTOR segment 记录')

# 4. 验证数据完整性
print('\n=== 4. 验证数据 ===')
count = cursor.execute('SELECT COUNT(*) FROM embeddings;').fetchone()
print(f'  Embeddings: {count[0]}')
count = cursor.execute('SELECT COUNT(*) FROM embedding_metadata;').fetchone()
print(f'  Metadata: {count[0]}')

result = cursor.execute('PRAGMA integrity_check;').fetchone()
print(f'  完整性: {result[0]}')

conn.close()

print('\n=== 完成 ===')
print('重启 Dashboard，ChromaDB 会重建 HNSW 索引')
print('注意：首次查询可能较慢，因为需要重建索引')

"""删除损坏的 FTS5 表，让 ChromaDB 自动重建"""
import sqlite3
import shutil
import os

db_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma_backup.sqlite3'

# 先备份
backup_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma_backup2.sqlite3'
shutil.copy(db_path, backup_path)
print(f'已备份到: {backup_path}')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=== 删除 FTS5 相关表 ===')

# 所有 FTS5 相关表
fts_tables = [
    'embedding_fulltext_search',
    'embedding_fulltext_search_data',
    'embedding_fulltext_search_idx',
    'embedding_fulltext_search_content',
    'embedding_fulltext_search_docsize',
    'embedding_fulltext_search_config',
]

for table in fts_tables:
    try:
        cursor.execute(f'DROP TABLE IF EXISTS {table};')
        print(f'  删除: {table}')
    except Exception as e:
        print(f'  删除 {table} 失败: {e}')

conn.commit()

# 验证数据完整性
print('\n=== 验证数据 ===')
count = cursor.execute('SELECT COUNT(*) FROM embeddings;').fetchone()
print(f'  Embeddings: {count[0]}')

count = cursor.execute('SELECT COUNT(*) FROM embedding_metadata;').fetchone()
print(f'  Metadata: {count[0]}')

# 检查完整性
result = cursor.execute('PRAGMA integrity_check;').fetchone()
print(f'  完整性: {result[0]}')

conn.close()

# 用修复后的文件替换原文件
original_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma.sqlite3'
if os.path.exists(original_path):
    os.remove(original_path)
shutil.move(db_path, original_path)
print(f'\n已修复并替换原数据库文件')
print('重启 Dashboard，ChromaDB 会自动重建 FTS5 索引')

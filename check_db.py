import sqlite3

conn = sqlite3.connect(r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma_backup.sqlite3')
cursor = conn.cursor()

# 检查数据库完整性
print('=== Integrity Check ===')
result = cursor.execute('PRAGMA integrity_check;').fetchall()
print(result)

# 检查表结构
print('\n=== Tables ===')
tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
for t in tables:
    print(t[0])

# 检查向量数据
print('\n=== Data Counts ===')
try:
    count = cursor.execute('SELECT COUNT(*) FROM embeddings;').fetchone()
    print(f'Embeddings: {count[0] if count else 0}')
except Exception as e:
    print(f'Embeddings table error: {e}')

try:
    count = cursor.execute('SELECT COUNT(*) FROM segments;').fetchone()
    print(f'Segments: {count[0] if count else 0}')
except Exception as e:
    print(f'Segments table error: {e}')

conn.close()

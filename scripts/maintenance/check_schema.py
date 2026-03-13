import sqlite3

db_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma_backup.sqlite3'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 查看 embeddings 表结构
print('=== embeddings 表结构 ===')
cols = cursor.execute('PRAGMA table_info(embeddings);').fetchall()
for col in cols:
    print(f'  {col[1]}: {col[2]}')

# 查看样本数据
print('\n=== 样本数据 ===')
sample = cursor.execute('SELECT * FROM embeddings LIMIT 1;').fetchone()
if sample:
    # 获取列名
    col_names = [desc[0] for desc in cursor.description]
    for name, val in zip(col_names, sample):
        print(f'  {name}: {str(val)[:100]}...' if len(str(val)) > 100 else f'  {name}: {val}')

conn.close()

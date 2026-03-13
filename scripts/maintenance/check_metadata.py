import sqlite3

db_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma_backup.sqlite3'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 查看 embedding_metadata 表结构
print('=== embedding_metadata 表结构 ===')
cols = cursor.execute('PRAGMA table_info(embedding_metadata);').fetchall()
for col in cols:
    print(f'  {col[1]}: {col[2]}')

# 查看样本数据
print('\n=== 样本数据 ===')
sample = cursor.execute('SELECT * FROM embedding_metadata LIMIT 3;').fetchall()
if sample:
    col_names = [desc[0] for desc in cursor.description]
    for row in sample:
        print('---')
        for name, val in zip(col_names, row):
            val_str = str(val)[:100] + '...' if len(str(val)) > 100 else str(val)
            print(f'  {name}: {val_str}')

# 统计
count = cursor.execute('SELECT COUNT(*) FROM embedding_metadata;').fetchone()
print(f'\n总记录数: {count[0]}')

conn.close()

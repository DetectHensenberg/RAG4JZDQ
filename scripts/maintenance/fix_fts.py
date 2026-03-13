"""修复 ChromaDB FTS5 索引损坏问题"""
import sqlite3

db_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma_backup.sqlite3'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=== 修复 FTS5 索引 ===')

# 1. 删除损坏的 FTS5 表
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
        print(f'  已删除: {table}')
    except Exception as e:
        print(f'  删除 {table} 失败: {e}')

conn.commit()

# 2. 重新创建 FTS5 索引
print('\n=== 重建 FTS5 索引 ===')
try:
    # ChromaDB 使用的 FTS5 表结构
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS embedding_fulltext_search USING fts5(
            string_value,
            content='embeddings',
            content_rowid='id',
            tokenize='porter'
        );
    ''')
    print('  创建 FTS5 表成功')
    
    # 重建索引
    cursor.execute('''
        INSERT INTO embedding_fulltext_search(embedding_fulltext_search) 
        VALUES('rebuild');
    ''')
    print('  重建索引成功')
    
    conn.commit()
    
    # 验证
    count = cursor.execute('SELECT COUNT(*) FROM embedding_fulltext_search;').fetchone()
    print(f'\n=== 结果 ===')
    print(f'  FTS5 索引记录数: {count[0]}')
    
    # 再次检查完整性
    result = cursor.execute('PRAGMA integrity_check;').fetchone()
    print(f'  数据库完整性: {result[0]}')
    
except Exception as e:
    print(f'  重建失败: {e}')
    conn.rollback()

conn.close()
print('\n修复完成！')

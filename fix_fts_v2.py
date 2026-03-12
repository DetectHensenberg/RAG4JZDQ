"""修复 ChromaDB FTS5 索引 - 正确版本"""
import sqlite3

db_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma_backup.sqlite3'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=== 修复 FTS5 索引 ===')

# ChromaDB 的 FTS5 是对 embedding_metadata 表的 string_value 建索引
# 外键关联到 embeddings 表

try:
    # 重建 FTS5 表（使用正确的结构）
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS embedding_fulltext_search USING fts5(
            string_value,
            content='embedding_metadata',
            content_rowid='id',
            tokenize='porter unicode61'
        );
    ''')
    print('  创建 FTS5 表成功')
    
    # 重建索引内容
    cursor.execute('''
        INSERT INTO embedding_fulltext_search(rowid, string_value)
        SELECT id, string_value FROM embedding_metadata WHERE string_value IS NOT NULL;
    ''')
    print('  填充索引数据成功')
    
    conn.commit()
    
    # 验证
    count = cursor.execute('SELECT COUNT(*) FROM embedding_fulltext_search;').fetchone()
    print(f'\n=== 结果 ===')
    print(f'  FTS5 索引记录数: {count[0]}')
    
    # 检查完整性
    result = cursor.execute('PRAGMA integrity_check;').fetchone()
    print(f'  数据库完整性: {result[0]}')
    
except Exception as e:
    print(f'  修复失败: {e}')
    conn.rollback()
    raise

conn.close()
print('\n修复完成！')

"""正确重建 BM25 索引"""
import json
import sqlite3
import os
import shutil
import jieba
from collections import Counter
from pathlib import Path

# 路径配置
chroma_path = r'D:\WorkSpace\project\个人项目\RAG\data\db\chroma\chroma.sqlite3'
bm25_dir = r'D:\WorkSpace\project\个人项目\RAG\data\db\bm25\default'
bm25_json = os.path.join(bm25_dir, 'default_bm25.json')

print('=== 1. 从 ChromaDB 读取数据 ===')
conn = sqlite3.connect(chroma_path)
cursor = conn.cursor()

# 获取所有 embedding_id 和对应的 text
embeddings = cursor.execute('''
    SELECT e.embedding_id, em.string_value 
    FROM embeddings e
    JOIN embedding_metadata em ON e.id = em.id
    WHERE em.key = 'text' AND em.string_value IS NOT NULL
''').fetchall()

print(f'  找到 {len(embeddings)} 条记录')
conn.close()

print('\n=== 2. 生成分词统计 ===')
term_stats = []
for emb_id, text in embeddings:
    if text:
        # 中文分词
        tokens = list(jieba.cut(text))
        term_freq = Counter(tokens)
        # 过滤停用词和单字
        term_freq = {k: v for k, v in term_freq.items() if len(k) > 1 and k.strip()}
        
        term_stats.append({
            'chunk_id': emb_id,
            'term_frequencies': dict(term_freq),
            'doc_length': len(tokens)
        })

print(f'  生成了 {len(term_stats)} 条统计')

print('\n=== 3. 构建 BM25 索引 ===')
# 计算语料库统计
num_docs = len(term_stats)
total_length = sum(stat['doc_length'] for stat in term_stats)
avg_doc_length = total_length / num_docs if num_docs > 0 else 0.0

# 计算文档频率
doc_freq = {}
for stat in term_stats:
    for term in stat['term_frequencies'].keys():
        doc_freq[term] = doc_freq.get(term, 0) + 1

print(f'  文档数: {num_docs}')
print(f'  平均长度: {avg_doc_length:.2f}')
print(f'  词项数: {len(doc_freq)}')

# 构建倒排索引
index = {}
k1 = 1.5
b = 0.75

for term, df in doc_freq.items():
    # IDF 计算
    idf = ((num_docs - df + 0.5) / (df + 0.5) + 1) * 1.0
    
    # 构建倒排表
    postings = []
    for stat in term_stats:
        tf = stat['term_frequencies'].get(term, 0)
        if tf > 0:
            postings.append({
                'chunk_id': stat['chunk_id'],
                'tf': tf,
                'doc_length': stat['doc_length']
            })
    
    index[term] = {
        'idf': idf,
        'df': df,
        'postings': postings
    }

# 元数据
metadata = {
    'num_docs': num_docs,
    'avg_doc_length': avg_doc_length,
    'total_terms': len(index)
}

print('\n=== 4. 备份旧索引 ===')
if os.path.exists(bm25_json):
    backup_path = bm25_json + '.backup2'
    shutil.copy(bm25_json, backup_path)
    print(f'  已备份到: {backup_path}')

print('\n=== 5. 写入新索引 ===')
data = {
    'metadata': metadata,
    'index': index
}

with open(bm25_json, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)

print(f'  写入完成: {os.path.getsize(bm25_json)} bytes')

print('\n=== 6. 验证 ===')
with open(bm25_json, 'r', encoding='utf-8') as f:
    loaded = json.load(f)
    print(f'  metadata: {loaded["metadata"]}')
    print(f'  index 词项数: {len(loaded["index"])}')
    # 样本词项
    sample_term = list(loaded['index'].keys())[0]
    print(f'  样本词项 "{sample_term}": idf={loaded["index"][sample_term]["idf"]:.2f}, postings={len(loaded["index"][sample_term]["postings"])}')

print('\n=== 完成 ===')
print('BM25 索引已正确重建，重启 Dashboard 后生效')

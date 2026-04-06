import sys
import os
import json
import logging
from pathlib import Path
from tqdm import tqdm
import fitz  # PyMuPDF

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.settings import load_settings
from src.libs.llm.openai_llm import OpenAILLM
from src.libs.llm.base_llm import Message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def translate_blocks(api_key: str, text_blocks: list) -> list:
    """批量翻译文本块。如果不满一批或达到限制，打包送去大模型翻译"""
    if not text_blocks:
        return []
    
    # 构建包含所有文本块编号的提示词
    payload = []
    for i, b in enumerate(text_blocks):
        text = b.get('text', '').strip()
        if text:
            payload.append({"id": i, "text": text})
            
    if not payload:
        return []
        
    prompt = f"""You are a professional English to Chinese translator. Please translate the following text blocks into natural, fluent Chinese.
Keep the original meaning, but adapt to Chinese reading habits. 

Input JSON format:
{json.dumps(payload, ensure_ascii=False)}

Return your translation strictly in the following JSON format without any other conversation:
[
  {{"id": 0, "translation": "中文翻译..."}},
  ...
]"""

    import requests
    try:
        url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "qwen-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0
        }
        logger.info(f"Sending {len(payload)} blocks to LLM (Prompt length: {len(prompt)} chars)...")
        res = requests.post(url, headers=headers, json=data, timeout=30)
        res.raise_for_status()
        
        content = res.json()["choices"][0]["message"]["content"]
        
        # Parse JSON from content (it might have markdown code blocks)
        content = content.replace('```json', '').replace('```', '').strip()
        result = json.loads(content)
        
        # Maps id -> translation
        trans_map = {item['id']: item['translation'] for item in result}
        return trans_map
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return {}

def process_pdf(pdf_path: str, output_path: str):
    logger.info(f"Loading settings...")
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=project_root / ".env", override=True)
    settings = load_settings(project_root / "config" / "settings.yaml")
    
    actual_key = os.environ.get('EMBEDDING_API_KEY')
    logger.info(f"Loaded actual_key prefix (EMBEDDING_API_KEY): {actual_key[:6] if actual_key else str(actual_key)}")
    
    logger.info(f"Opening PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    
    # 我们使用黑体或雅黑字体
    font_path = "C:/Windows/Fonts/simhei.ttf"
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/msyh.ttc"
        
    md_output_file = output_path.replace('.pdf', '') + '.md'
    with open(md_output_file, 'w', encoding='utf-8') as f:
        f.write("# US-UAV+规划2005-2030 中文翻译副本\n\n")

    for page_num in tqdm(range(len(doc)), desc="Translating pages"):
        page = doc[page_num]
        
        # 获取所有 text block
        blocks = page.get_text("dict")["blocks"]
        text_blocks = []
        for b in blocks:
            if b['type'] == 0:  # Text block
                text = ""
                for line in b["lines"]:
                    for span in line["spans"]:
                        text += span["text"] + " "
                if text.strip() and len(text.strip()) > 2:
                    text_blocks.append({
                        "bbox": b["bbox"],
                        "text": text.strip()
                    })
                    
        if not text_blocks:
            continue
            
        trans_map = translate_blocks(actual_key, text_blocks)
        
        # 同时追加写入 Markdown 副本作为双重保险
        with open(md_output_file, 'a', encoding='utf-8') as f:
            f.write(f"\n\n## 第 {page_num+1} 页\n\n")
            for idx in range(len(text_blocks)):
                if idx in trans_map and trans_map[idx]:
                    f.write(f"- {trans_map[idx]}\n")
            
        # 覆写文字
        for idx_raw, translated_text in trans_map.items():
            if not translated_text:
                continue
            
            # 由于大模型偶尔会产生幻觉顺口编造不存在的块 id ，所以这里拦截越界提取防止脚本崩溃
            try:
                idx = int(idx_raw)
            except ValueError:
                continue
                
            if idx < 0 or idx >= len(text_blocks):
                logger.warning(f"Skipping hallucinated block ID from LLM: {idx}")
                continue
                
            b = text_blocks[idx]
            rect = fitz.Rect(b["bbox"])
            
            # 使用白色实心矩形覆盖原本的区域
            page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
            
            # 插入中文
            try:
                page.insert_textbox(rect, translated_text, fontfile=font_path, fontsize=10, color=(0, 0, 0))
            except Exception as e:
                logger.warning(f"Failed to insert text at page {page_num}: {e}")
                
    logger.info(f"Saving translated PDF to {output_path}")
    doc.save(output_path)
    doc.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Translate PDF from EN to ZH and overwrite")
    parser.add_argument("--input", required=True, help="Input PDF path")
    parser.add_argument("--output", required=True, help="Output PDF path")
    args = parser.parse_args()
    
    process_pdf(args.input, args.output)
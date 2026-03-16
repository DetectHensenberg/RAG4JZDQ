"""Test which vision models are supported on coding endpoint."""
import httpx

KEY = "sk-sp-e263371071d94db7b27f5acd132c4ec9"
URL = "https://coding.dashscope.aliyuncs.com/v1/chat/completions"

models = [
    "qwen-vl-max",
    "qwen-vl-plus",
    "qwen-vl-plus-latest",
    "qwen2.5-vl-plus",
    "qwen2.5-vl-max",
    "qwen-vl-max-latest",
    "qwen2-vl-7b-instruct",
]

for m in models:
    r = httpx.post(
        URL,
        json={
            "model": m,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            "max_tokens": 5,
        },
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    status = "OK" if r.status_code == 200 else f"FAIL({r.status_code})"
    print(f"  {m}: {status}")

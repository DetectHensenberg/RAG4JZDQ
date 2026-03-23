import asyncio
import json
import time
import sys
import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class BenchResult:
    concurrency: int
    total_requests: int
    success_count: int
    error_count: int
    avg_latency: float
    p95_latency: float
    errors: List[str]

class MCPBenchmarker:
    """Benchmark MCP server via stdio transport."""
    
    def __init__(self, server_script: str, python_exe: str = sys.executable):
        self.server_script = server_script
        self.python_exe = python_exe

    async def _run_single_query(self, query: str, request_id: int) -> Dict[str, Any]:
        """Run a single tool call via a fresh server process."""
        start_time = time.perf_counter()
        
        # Start server
        process = await asyncio.create_subprocess_exec(
            self.python_exe, self.server_script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": os.getcwd()}
        )
        
        stderr_output = []
        
        async def read_stderr():
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                stderr_output.append(line.decode().strip())

        stderr_task = asyncio.create_task(read_stderr())
        
        try:
            # Helper to read stdout until a specific JSON-RPC response ID is found
            async def read_response(target_id: Optional[int], timeout: int = 60) -> Dict[str, Any]:
                start_read = time.time()
                while time.time() - start_read < timeout:
                    try:
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
                        if not line:
                            break
                        try:
                            resp = json.loads(line.decode())
                            # If target_id is None, we return the first JSON-RPC message
                            if target_id is None or resp.get("id") == target_id:
                                return resp
                        except json.JSONDecodeError:
                            continue
                    except asyncio.TimeoutError:
                        if process.returncode is not None:
                            break
                        continue
                raise TimeoutError(f"Timed out waiting for ID {target_id}. Last stderr: {stderr_output[-3:] if stderr_output else 'N/A'}")

            # 1. Initialize
            init_request = {
                "jsonrpc": "2.0",
                "id": 1000 + request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "benchmarker", "version": "1.0.0"}
                }
            }
            process.stdin.write(json.dumps(init_request).encode() + b"\n")
            await process.stdin.drain()
            await read_response(1000 + request_id)
            
            # 2. Initialized notification
            initialized_notif = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            process.stdin.write(json.dumps(initialized_notif).encode() + b"\n")
            await process.stdin.drain()

            # 3. Tool call
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "query_knowledge_hub",
                    "arguments": {"query": query, "top_k": 3}
                },
                "id": request_id
            }
            
            tool_start = time.perf_counter()
            process.stdin.write(json.dumps(request).encode() + b"\n")
            await process.stdin.drain()
            
            response = await read_response(request_id, timeout=120) # Tools can be slow
            latency = time.perf_counter() - tool_start
            
            # Check for error
            has_error = "error" in response
            if not has_error and "result" in response:
                result = response["result"]
                if result.get("isError"):
                    has_error = True
            
            return {
                "success": not has_error,
                "error": response.get("error") or response.get("result", {}).get("content"),
                "latency": latency
            }
        except Exception as e:
            return {
                "success": False, 
                "error": f"{str(e)} | Stderr: {' '.join(stderr_output)}", 
                "latency": time.perf_counter() - start_time
            }
        finally:
            stderr_task.cancel()
            if process.returncode is None:
                process.terminate()
            await process.wait()

    async def run_benchmark(self, concurrency: int, queries: List[str]) -> BenchResult:
        """Run benchmark with specified concurrency."""
        print(f"Running benchmark with concurrency={concurrency}...")
        
        tasks = []
        # Use different queries for concurrency
        for i in range(concurrency):
            query = queries[i % len(queries)]
            tasks.append(self._run_single_query(query, i))
            
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        
        latencies = [r["latency"] for r in results]
        success_count = sum(1 for r in results if r.get("success"))
        errors = [str(r.get("error")) for r in results if not r.get("success")]
        
        latencies.sort()
        p95_idx = int(len(latencies) * 0.95) if latencies else 0
        
        return BenchResult(
            concurrency=concurrency,
            total_requests=len(results),
            success_count=success_count,
            error_count=len(errors),
            avg_latency=sum(latencies) / len(latencies) if latencies else 0,
            p95_latency=latencies[p95_idx] if latencies else 0,
            errors=errors[:10]
        )

async def main():
    benchmarker = MCPBenchmarker("src/mcp_server/server.py")
    
    queries = [
        "什么是全量检索？",
        "如何配置 Azure OpenAI？",
        "介绍一下本项目的设计理念",
        "GraphRAG 的核心优势是什么？",
        "怎么使用 Parent Retrieval？",
        "反馈落库是如何实现的？"
    ]
    
    levels = [1, 3] # Keep it smaller for baseline to avoid too long wait
    final_report = "# Concurrency Benchmark Report\n\n"
    
    for c in levels:
        res = await benchmarker.run_benchmark(c, queries)
        report = f"### Concurrency: {res.concurrency}\n"
        report += f"- Success: {res.success_count}/{res.total_requests}\n"
        report += f"- Avg Latency: {res.avg_latency:.2f}s\n"
        report += f"- P95 Latency: {res.p95_latency:.2f}s\n"
        if res.errors:
            report += f"- Samples Errors: {res.errors[0]}...\n"
        report += "\n"
        print(report)
        final_report += report
        
    with open("docs/PerformanceTesting/BASELINE_REPORT.md", "w", encoding="utf-8") as f:
        f.write(final_report)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import json
import os
import sys

async def debug_mcp():
    process = await asyncio.create_subprocess_exec(
        sys.executable, "src/mcp_server/server.py",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": os.getcwd()}
    )
    
    async def read_stream(name, stream):
        while True:
            try:
                line = await stream.readline()
                if not line:
                    print(f"[{name}] EOF")
                    break
                print(f"[{name}] {line.decode().strip()}")
            except Exception as e:
                print(f"[{name}] Error: {e}")
                break

    asyncio.create_task(read_stream("STDOUT", process.stdout))
    asyncio.create_task(read_stream("STDERR", process.stderr))

    print("[SYSTEM] Process started, waiting for preload...")
    await asyncio.sleep(5)
    
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0.0"}
        }
    }
    print("[STDIN] Sending initialize...")
    process.stdin.write(json.dumps(init_request).encode() + b"\n")
    await process.stdin.drain()
    
    print("[SYSTEM] Waiting for initialize response...")
    await asyncio.sleep(10)
    
    init_notif = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }
    print("[STDIN] Sending initialized notification...")
    process.stdin.write(json.dumps(init_notif).encode() + b"\n")
    await process.stdin.drain()

    print("[SYSTEM] Done, waiting 5s then exiting...")
    await asyncio.sleep(5)
    if process.returncode is None:
        process.terminate()
    await process.wait()

if __name__ == "__main__":
    asyncio.run(debug_mcp())

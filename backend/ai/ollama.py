import json
import os
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from typing import AsyncGenerator

load_dotenv()

OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "exaone3.5:7.8b")


async def call_ollama(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            res = await client.post(OLLAMA_URL, json={
                "model":  OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            })
            res.raise_for_status()
            return res.json().get("response", "")
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="LLM 서버에 연결할 수 없습니다. Ollama가 실행 중인지 확인하세요.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="LLM 응답 시간이 초과되었습니다. (120초)",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM 서버 오류: {e.response.status_code}",
        )


async def stream_ollama(prompt: str) -> AsyncGenerator[str, None]:
    """Ollama stream=True로 호출해 텍스트 청크를 순서대로 yield."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", OLLAMA_URL, json={
                "model":  OLLAMA_MODEL,
                "prompt": prompt,
                "stream": True,
                "format": "json",
            }) as res:
                res.raise_for_status()
                async for line in res.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        return
    except httpx.ConnectError:
        raise RuntimeError("LLM 서버에 연결할 수 없습니다. Ollama가 실행 중인지 확인하세요.")
    except httpx.TimeoutException:
        raise RuntimeError("LLM 응답 시간이 초과되었습니다. (120초)")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"LLM 서버 오류: {e.response.status_code}")

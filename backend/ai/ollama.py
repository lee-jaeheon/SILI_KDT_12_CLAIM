import httpx
from fastapi import HTTPException

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "exaone3.5:7.8b"


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

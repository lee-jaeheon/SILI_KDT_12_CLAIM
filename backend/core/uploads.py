from fastapi import HTTPException, UploadFile

MAX_IMAGE_MB = 5
MAX_DOC_MB = 10


def _too_large(max_mb: int) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"파일 크기가 너무 큽니다. (최대 {max_mb}MB)",
    )


def check_size(file: UploadFile, max_mb: int) -> None:
    size = getattr(file, "size", None)
    if size is not None and size > max_mb * 1024 * 1024:
        raise _too_large(max_mb)


async def read_with_limit(file: UploadFile, max_mb: int) -> bytes:
    check_size(file, max_mb)
    data = await file.read()
    if len(data) > max_mb * 1024 * 1024:
        raise _too_large(max_mb)
    return data

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from backend.models.database import get_conn

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_SECRET       = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET 환경변수가 설정되지 않았습니다. "
        ".env 또는 start.bat에 'JWT_SECRET=<랜덤긴문자열>' 추가하세요."
    )
JWT_ALGORITHM    = "HS256"
JWT_EXPIRE_HOURS = 8

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security    = HTTPBearer(auto_error=False)


# ── 유틸 ────────────────────────────────────────────────────────────────────────

def hash_pw(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_pw(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def make_token(payload: dict) -> str:
    data = payload.copy()
    data["exp"] = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ── 인증 의존성 ─────────────────────────────────────────────────────────────────

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    # DB 재검증: 비활성화/삭제/role 변경 즉시 반영
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username, name, role, is_active FROM users WHERE user_id = %s",
                (user_id,),
            )
            user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="존재하지 않는 사용자입니다.")
    if not user["is_active"]:
        raise HTTPException(status_code=401, detail="비활성화된 계정입니다.")

    # DB의 최신 role을 권위로 사용 (토큰 payload 안의 role 무시)
    return {
        "user_id":  user["user_id"],
        "username": user["username"],
        "name":     user["name"],
        "role":     user["role"],
    }

def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user


# ── 요청 스키마 ─────────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    username: str
    password: str

class RegisterBody(BaseModel):
    username: str
    password: str
    name: str


# ── 로그인 ─────────────────────────────────────────────────────────────────────

@router.post("/login")
def login(body: LoginBody):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE username = %s AND is_active = 1",
                (body.username,),
            )
            user = cur.fetchone()

    if not user or not verify_pw(body.password, user["password"]):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    token = make_token({
        "user_id":  user["user_id"],
        "username": user["username"],
        "name":     user["name"] or user["username"],
        "role":     user["role"],
    })
    return {
        "token": token,
        "user": {
            "user_id":  user["user_id"],
            "username": user["username"],
            "name":     user["name"] or user["username"],
            "role":     user["role"],
        },
    }


# ── 회원가입 ───────────────────────────────────────────────────────────────────

@router.post("/register")
def register(body: RegisterBody):
    if len(body.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="아이디는 3자 이상이어야 합니다.")
    if len(body.password) < 4:
        raise HTTPException(status_code=400, detail="비밀번호는 4자 이상이어야 합니다.")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="이름을 입력해주세요.")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM users WHERE username = %s",
                (body.username.strip(),),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")
            cur.execute(
                "INSERT INTO users (username, password, name, role) VALUES (%s, %s, %s, 'user')",
                (body.username.strip(), hash_pw(body.password), body.name.strip()),
            )
    return {"message": "회원가입이 완료됐습니다."}


# ── 관리자: 계정 목록 ──────────────────────────────────────────────────────────

@router.get("/users")
def list_users(_: dict = Depends(require_admin)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username, name, role, is_active, created_at "
                "FROM users ORDER BY user_id"
            )
            return cur.fetchall()


# ── 관리자: 활성화/비활성화 토글 ───────────────────────────────────────────────

@router.patch("/users/{user_id}/status")
def toggle_status(user_id: int, _: dict = Depends(require_admin)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, is_active FROM users WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
            if row["role"] == "admin":
                raise HTTPException(status_code=400, detail="관리자 계정은 비활성화할 수 없습니다.")
            new_status = 0 if row["is_active"] else 1
            cur.execute(
                "UPDATE users SET is_active = %s WHERE user_id = %s",
                (new_status, user_id),
            )
    return {"is_active": new_status}


# ── 관리자: 역할 변경 ──────────────────────────────────────────────────────────

@router.patch("/users/{user_id}/role")
def toggle_role(user_id: int, _: dict = Depends(require_admin)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
            new_role = "admin" if row["role"] == "user" else "user"
            cur.execute(
                "UPDATE users SET role = %s WHERE user_id = %s",
                (new_role, user_id),
            )
    return {"role": new_role}


# ── 관리자: 계정 삭제 ──────────────────────────────────────────────────────────

@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: dict = Depends(require_admin)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
            if row["role"] == "admin":
                raise HTTPException(status_code=400, detail="관리자 계정은 삭제할 수 없습니다.")
            if user_id == admin.get("user_id"):
                raise HTTPException(status_code=400, detail="본인 계정은 삭제할 수 없습니다.")
            cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
    return {"message": "계정이 삭제됐습니다."}

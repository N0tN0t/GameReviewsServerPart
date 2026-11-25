from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.repositories import UserRepository
from src.infrastructure.security import create_access_token, hash_password, verify_password
from src.presentation.dependencies import get_db_session, rate_limit
from src.presentation.schemas import LoginSchema, RegisterSchema, TokenResponseSchema

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponseSchema, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterSchema, session: AsyncSession = Depends(get_db_session)):
    repo = UserRepository(session)
    if await repo.get_by_email(body.email) or await repo.get_by_username(body.username):
        raise HTTPException(
            status_code=409, detail="Пользователь с таким email или логином уже есть"
        )

    user = await repo.create(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    return TokenResponseSchema(access_token=create_access_token(user.id, user.role))


@router.post(
    "/login",
    response_model=TokenResponseSchema,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))],
)
async def login(body: LoginSchema, session: AsyncSession = Depends(get_db_session)):
    repo = UserRepository(session)
    user = await repo.get_by_email(body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    return TokenResponseSchema(access_token=create_access_token(user.id, user.role))

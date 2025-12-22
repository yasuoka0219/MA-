"""API dependencies - authentication and database session"""
from typing import Annotated
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.database import get_db
from src.ma_tool.models.user import User


def get_current_user(
    db: Session = Depends(get_db),
    x_user_id: int = Header(default=1, description="User ID for simple auth")
) -> User:
    user = db.execute(
        select(User).where(User.id == x_user_id, User.is_active == True)
    ).scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]

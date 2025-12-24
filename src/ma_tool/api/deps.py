"""API dependencies - authentication and database session"""
from typing import Annotated, Optional
from functools import wraps
from fastapi import Depends, HTTPException, Header, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.database import get_db
from src.ma_tool.models.user import User, UserRole


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


def get_session_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    ).scalar_one_or_none()
    return user


def require_session_login(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_session_user(request, db)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/ui/login"})
    return user


def require_role(*roles: UserRole):
    def dependency(user: User = Depends(require_session_login)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dependency


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def require_editor_or_admin(current_user: User = Depends(get_current_user)) -> User:
    """Editor can create/edit templates, Admin can do everything"""
    if current_user.role not in [UserRole.ADMIN, UserRole.EDITOR]:
        raise HTTPException(status_code=403, detail="Editor or Admin access required")
    return current_user


def require_approver_or_admin(current_user: User = Depends(get_current_user)) -> User:
    """Approver can approve/reject templates, Admin can do everything"""
    if current_user.role not in [UserRole.ADMIN, UserRole.APPROVER]:
        raise HTTPException(status_code=403, detail="Approver or Admin access required")
    return current_user


def can_edit_template(user: User) -> bool:
    """Check if user can edit templates (editor or admin)"""
    return user.role in [UserRole.ADMIN, UserRole.EDITOR]


def can_approve_template(user: User) -> bool:
    """Check if user can approve/reject templates (approver or admin)"""
    return user.role in [UserRole.ADMIN, UserRole.APPROVER]


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
EditorUser = Annotated[User, Depends(require_editor_or_admin)]
ApproverUser = Annotated[User, Depends(require_approver_or_admin)]
AdminUser = Annotated[User, Depends(require_admin)]

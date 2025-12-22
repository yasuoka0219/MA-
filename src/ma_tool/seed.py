"""Seed data for initial setup"""
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ma_tool.database import SessionLocal
from src.ma_tool.models.user import User, UserRole


def create_admin_user(db: Session) -> User:
    existing = db.execute(
        select(User).where(User.email == "admin@example.com")
    ).scalar_one_or_none()
    
    if existing:
        print("Admin user already exists")
        return existing
    
    admin = User(
        email="admin@example.com",
        name="System Admin",
        role=UserRole.ADMIN,
        is_active=True
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    print(f"Created admin user: {admin.email} (ID: {admin.id})")
    return admin


def run_seed():
    db = SessionLocal()
    try:
        create_admin_user(db)
        print("Seed completed successfully")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()

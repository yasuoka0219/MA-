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


def create_test_users(db: Session) -> list[User]:
    users_data = [
        ("editor@example.com", "Editor User", UserRole.EDITOR),
        ("approver@example.com", "Approver User", UserRole.APPROVER),
        ("viewer@example.com", "Viewer User", UserRole.VIEWER),
    ]
    
    created = []
    for email, name, role in users_data:
        existing = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        
        if existing:
            print(f"{role.value} user already exists: {email}")
            created.append(existing)
            continue
        
        user = User(
            email=email,
            name=name,
            role=role,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created {role.value} user: {email} (ID: {user.id})")
        created.append(user)
    
    return created


def run_seed():
    db = SessionLocal()
    try:
        create_admin_user(db)
        create_test_users(db)
        print("Seed completed successfully")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()

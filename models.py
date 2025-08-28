# schemas.py  (or models.py)

from sqlalchemy import Column, Integer, String         
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel, EmailStr

Base = declarative_base()

# ---------- SQLAlchemy ORM model ----------
class Admin(Base):
    __tablename__ = "admin"
    id       = Column(Integer, primary_key=True, index=True)
    email    = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)

# ---------- Pydantic schemas ----------
class AdminCreate(BaseModel):
    email:    EmailStr
    password: str

class AdminOut(BaseModel):
    id:    int
    email: EmailStr

    class Config:
        orm_mode = True

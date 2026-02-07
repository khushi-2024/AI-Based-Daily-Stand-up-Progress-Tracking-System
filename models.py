# models.py
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Team(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    lead_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Standup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    team_id: int = Field(foreign_key="team.id")
    user_name: str
    yesterday: str
    today: str
    blockers: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

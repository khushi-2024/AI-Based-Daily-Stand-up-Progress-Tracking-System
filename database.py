# database.py
from sqlmodel import SQLModel, create_engine, Session

# SQLite database file
DATABASE_URL = "sqlite:///./standup.db"

# create engine
engine = create_engine(DATABASE_URL, echo=True)

# initialize DB
def init_db():
    SQLModel.metadata.create_all(engine)

# session generator
def get_session():
    with Session(engine) as session:
        yield session

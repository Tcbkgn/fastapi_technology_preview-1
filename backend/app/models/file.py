from sqlalchemy import Boolean, Column, Integer, String
from files.db import Base

class FileItem(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    checksum = Column(String, index=True)
    size = Column(Integer)

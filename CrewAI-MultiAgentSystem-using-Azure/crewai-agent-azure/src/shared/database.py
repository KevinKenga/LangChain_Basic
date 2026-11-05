'''
Database Service Module.
This module handles the connection to Azure PostgreSQL
It uses SQLAlchemy to define the tables and insert the data safely

example syntax
AZURE_POSTGRES_CONNECTION_STRING = 
"postgresql://projectonetest:YOUR_PASSWORD_HERE@project-chirantan-demo-001.postgres.database.azure.com:5432/postgres?sslmode=require"

'''
from sqlalchemy import create_engine, Column, Integer, String, Text,DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime,timezone
from src.shared.config import settings

Base = declarative_base()

# Define the table schema
class FinancialReport(Base):
    __tablename__ = "reports_log"
    id = Column(Integer, primary_key = True, autoincrement = True)
    ticker = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default= lambda : datetime.now(timezone.utc))


# Define Database Manager class
class DatabaseService:
    def __init__(self):
        # Connect to Azure postgres
        # We need to ensure that the connection string startswith 'postgresql://'
        db_url = settings.azure_postgres_connection_string
        if db_url and db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://" , "postgresql://", 1)

        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create the tables if they dont exist 
        Base.metadata.create_all(bind= self.engine)
    
    def save_report(self,ticker:str, content:str):
        '''
        Saves the new analysis report to the database
        '''
        session = self.SessionLocal()
        try:
            new_report = FinancialReport(ticker=ticker, content=content)
            session.add(new_report)
            session.commit()
            print(f"Saved {ticker} report to Database (ID : {new_report.id})")
        except Exception as e:
            print(f"Database Error : {e}")
            session.rollback()
        finally:
            session.close()

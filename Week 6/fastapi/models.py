from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, DateTime
from sqlalchemy.orm import relationship
import datetime
from database import Base

class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    complete = Column(Boolean, default=False)

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)              # e.g., Apple Inc.
    sector = Column(String, index=True)             # e.g., Technology
    is_nasdaq_listed = Column(Boolean, default=True)

    stocks = relationship("Stock", back_populates="company")

class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, unique=True, index=True)   # e.g., AAPL, MSFT
    price = Column(Float, nullable=False)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)
    company_id = Column(Integer, ForeignKey("companies.id"))

    company = relationship("Company", back_populates="stocks")
    registrations = relationship("Registration", back_populates="stock")

class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    investor_name = Column(String, index=True)
    shares_owned = Column(Integer, default=0)
    is_active_position = Column(Boolean, default=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"))

    stock = relationship("Stock", back_populates="registrations")

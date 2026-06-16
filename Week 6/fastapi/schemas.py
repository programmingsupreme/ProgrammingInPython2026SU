from pydantic import BaseModel

class TodoCreate(BaseModel):
    title: str

class TodoUpdate(BaseModel):
    complete: bool

class CompanyCreate(BaseModel):
    name: str
    sector: str

class StockCreate(BaseModel):
    ticker: str
    price: float
    company_id: int

class RegistrationCreate(BaseModel):
    investor_name: str
    shares_owned: int
    stock_id: int

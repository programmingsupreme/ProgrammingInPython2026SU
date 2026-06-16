from fastapi import FastAPI, Depends, Request, Form, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import models, schemas
from database import SessionLocal, engine

# Initialize the app
app = FastAPI()

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Create the database tables
models.Base.metadata.create_all(bind=engine)

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize the database with sample NASDAQ companies and stocks
def init_db():
    db = SessionLocal()
    if db.query(models.Company).count() == 0:
        apple = models.Company(name="Apple Inc.", sector="Technology")
        microsoft = models.Company(name="Microsoft Corporation", sector="Technology")
        nvidia = models.Company(name="NVIDIA Corporation", sector="Semiconductors")
        tesla = models.Company(name="Tesla, Inc.", sector="Automotive")
        amazon = models.Company(name="Amazon.com, Inc.", sector="E-Commerce")
        db.add_all([apple, microsoft, nvidia, tesla, amazon])
        db.commit()

        sample_stocks = [
            models.Stock(ticker="AAPL", price=195.50, company_id=apple.id),
            models.Stock(ticker="MSFT", price=420.75, company_id=microsoft.id),
            models.Stock(ticker="NVDA", price=121.30, company_id=nvidia.id),
            models.Stock(ticker="TSLA", price=255.10, company_id=tesla.id),
            models.Stock(ticker="AMZN", price=185.90, company_id=amazon.id),
        ]
        db.add_all(sample_stocks)
        db.commit()
    db.close()

# Initialize the database with sample data
init_db()

@app.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    todos = db.query(models.Todo).all()
    return templates.TemplateResponse(request=request, name="index.html", context={"todo_list": todos})

@app.post("/add")
async def add(request: Request, title: str = Form(...), db: Session = Depends(get_db)):
    new_todo = models.Todo(title=title)
    db.add(new_todo)
    db.commit()
    url = app.url_path_for("home")
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)

@app.get("/update/{todo_id}")
async def update(request: Request, todo_id: int, db: Session = Depends(get_db)):
    todo = db.query(models.Todo).filter(models.Todo.id == todo_id).first()
    todo.complete = not todo.complete
    db.commit()
    url = app.url_path_for("home")
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)

@app.get("/delete/{todo_id}")
async def delete(request: Request, todo_id: int, db: Session = Depends(get_db)):
    todo = db.query(models.Todo).filter(models.Todo.id == todo_id).first()
    db.delete(todo)
    db.commit()
    url = app.url_path_for("home")
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)

@app.get("/registration")
async def registration(request: Request, db: Session = Depends(get_db)):
    stocks = db.query(models.Stock).all()
    registrations = db.query(models.Registration).all()
    return templates.TemplateResponse(request=request, name="registration.html", context={"stock_list": stocks, "registration_list": registrations})

@app.post("/register")
async def register(request: Request, investor_name: str = Form(...), shares_owned: int = Form(...), stock_id: int = Form(...), db: Session = Depends(get_db)):
    new_registration = models.Registration(investor_name=investor_name, shares_owned=shares_owned, stock_id=stock_id)
    db.add(new_registration)
    db.commit()
    url = app.url_path_for("registration")
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)

@app.get("/stocks")
async def stocks(request: Request, db: Session = Depends(get_db)):
    stocks = db.query(models.Stock).all()
    companies = db.query(models.Company).all()
    return templates.TemplateResponse(request=request, name="stocks.html", context={"stock_list": stocks, "company_list": companies})

@app.post("/add_stock")
async def add_stock(request: Request, ticker: str = Form(...), price: float = Form(...), company_id: int = Form(...), db: Session = Depends(get_db)):
    new_stock = models.Stock(ticker=ticker.upper(), price=price, company_id=company_id)
    db.add(new_stock)
    db.commit()
    url = app.url_path_for("stocks")
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)

@app.get("/companies")
async def companies(request: Request, db: Session = Depends(get_db)):
    companies = db.query(models.Company).all()
    return templates.TemplateResponse(request=request, name="companies.html", context={"company_list": companies})

@app.post("/add_company")
async def add_company(request: Request, company_name: str = Form(...), sector: str = Form(...), db: Session = Depends(get_db)):
    new_company = models.Company(name=company_name, sector=sector)
    db.add(new_company)
    db.commit()
    url = app.url_path_for("companies")
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)

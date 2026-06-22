# Flask To-Do App

A simple to-do list web app built with Flask and SQLite, based on the tutorial code.

## Project structure

```
.
├── app.py
├── requirements.txt
└── templates/
    └── base.html
```

## Setup & run

```bash
# 1. (optional) create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. install dependencies
pip install -r requirements.txt

# 3. run the app
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

## Features

- Add to-do items
- Mark items complete / undo
- Delete items
- Data persists in a local SQLite file (`instance/db.sqlite`)

## Note on the original code

The tutorial calls `db.create_all()` at module level, which raises a
`RuntimeError: Working outside of application context` on modern Flask /
Flask-SQLAlchemy. This version wraps it in an `app.app_context()` block inside
the `__main__` guard so the database table is created correctly on startup.

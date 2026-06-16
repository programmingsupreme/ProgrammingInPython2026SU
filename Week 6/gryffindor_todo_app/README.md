# Gryffindor To-Do App (Flask + SQLAlchemy)

A small to-do web app from the "Light Class activity: Flask" lab. Tasks are
stored in a SQLite database so they persist across restarts. You can add,
mark done/undo, delete, and clear all tasks.

## Project structure

```
gryffindor_todo_app/
├── app.py
├── requirements.txt
├── templates/
│   ├── base.html
│   └── index.html
└── static/
    └── style.css
```

## Run it

```bash
# 1. (optional but recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\activate

# 2. install dependencies
pip install -r requirements.txt

# 3. run
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

A `db.sqlite` file is created automatically on first run. To start fresh,
delete it and restart.

## Notes on the lab

The lab's source code calls `db.create_all()` at module level, which raises
a *"working outside of application context"* error in current
Flask-SQLAlchemy. This project wraps it in `with app.app_context():`, which
is the fix the later "ChatGPT to the rescue" step in the PDF was pointing at.
`db.session.get(Todo, id)` is used instead of the deprecated `Query.get()`.

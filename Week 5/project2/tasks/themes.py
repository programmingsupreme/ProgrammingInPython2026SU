"""Theme registry for the points shop.

Per project convention, theme *styling* is not authored here. Each purchasable
theme just points at a real, free, hosted stylesheet from Bootswatch
(https://bootswatch.com) -- a long-running site of ready-made Bootstrap themes,
served via the jsDelivr CDN. The app's own retrowave look
(static/tasks/css/style.css) is the default, always-unlocked theme; every other
option is fetched live in the visitor's browser via a <link> tag in base.html.
Nothing about a purchased theme's actual colors or fonts is hardcoded here --
this module only stores which theme maps to which URL, and how many points it
costs.
"""

BOOTSWATCH_VERSION = "5.3.3"
DEFAULT_THEME_KEY = "retrowave"


def _bootswatch_url(slug):
    return f"https://cdn.jsdelivr.net/npm/bootswatch@{BOOTSWATCH_VERSION}/dist/{slug}/bootstrap.min.css"


THEMES = [
    {
        "key": "retrowave",
        "name": "Retrowave (default)",
        "cost": 0,
        "css_url": None,
        "source_name": "Built-in",
        "source_url": None,
    },
    {
        "key": "cyborg",
        "name": "Cyborg",
        "cost": 30,
        "css_url": _bootswatch_url("cyborg"),
        "source_name": "Bootswatch",
        "source_url": "https://bootswatch.com/cyborg/",
    },
    {
        "key": "vapor",
        "name": "Vapor",
        "cost": 30,
        "css_url": _bootswatch_url("vapor"),
        "source_name": "Bootswatch",
        "source_url": "https://bootswatch.com/vapor/",
    },
    {
        "key": "darkly",
        "name": "Darkly",
        "cost": 50,
        "css_url": _bootswatch_url("darkly"),
        "source_name": "Bootswatch",
        "source_url": "https://bootswatch.com/darkly/",
    },
    {
        "key": "solar",
        "name": "Solar",
        "cost": 50,
        "css_url": _bootswatch_url("solar"),
        "source_name": "Bootswatch",
        "source_url": "https://bootswatch.com/solar/",
    },
    {
        "key": "superhero",
        "name": "Superhero",
        "cost": 70,
        "css_url": _bootswatch_url("superhero"),
        "source_name": "Bootswatch",
        "source_url": "https://bootswatch.com/superhero/",
    },
    {
        "key": "lux",
        "name": "Lux",
        "cost": 100,
        "css_url": _bootswatch_url("lux"),
        "source_name": "Bootswatch",
        "source_url": "https://bootswatch.com/lux/",
    },
]

THEMES_BY_KEY = {theme["key"]: theme for theme in THEMES}


def get_theme(key):
    """Look up a theme by key, falling back to the default if unknown."""
    return THEMES_BY_KEY.get(key, THEMES_BY_KEY[DEFAULT_THEME_KEY])


def is_valid_theme_key(key):
    return key in THEMES_BY_KEY

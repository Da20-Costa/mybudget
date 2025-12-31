import locale

from datetime import datetime
from flask import redirect, render_template, session
from functools import wraps
from translations import translations


def apology(message, code=400):
    """Render message as an apology to user."""
    lang = session.get("language", "en")
    translated_message = translations[lang].get(message, message)
    return render_template("apology.html", top=code, bottom=translated_message), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def format_currency(value):
    """Format value as currency based on the current language."""
    lang = session.get("language", "en")

    try:
        value = float(value)
    except:
        return ""
    
    if lang == 'pt':
        formatted =  f"{value:,.2f}"
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")

        return f"R$ {formatted}"
    
    else:
        return f"${value:,.2f}"

def format_date(value):
    """Format a date string based on the current language."""
    if value is None:
        return ""
    
    date_obj = value
    if isinstance(value, str):
        try:
            date_obj = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                date_obj = datetime.strptime(value, '%Y-%m-%d')
            except ValueError:
                return value

    lang = session.get("language", "en")

    if lang == "pt":
        return date_obj.strftime('%d/%m/%Y')
    else:
        return date_obj.strftime('%m/%d/%Y')

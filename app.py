import os
import locale

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, format_currency, format_date
from translations import translations


# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["format_currency"] = format_currency
app.jinja_env.filters['dateformat'] = format_date

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///budget.db")

# Auxiliar Function
def process_recurring_transactions(user_id):
    """Checks and adds recurring transactions for the current month if not already added."""

    current_month = datetime.now().strftime('%Y-%m') # '2025-10'

    # Get all user's recurring transaction rules
    recurring_rules = db.execute(
        "SELECT * FROM recurring_transactions WHERE user_id = ?", user_id
    )

    for rule in recurring_rules:
        # if the transaction wasn't added yet this month
        if rule["last_added"] != current_month:
            day = min(rule["day_of_month"], 28)
            transaction_date = f"{current_month}-{str(day).zfill(2)} 00:00:00"

            # Insert the transaction in the transactions table
            db.execute(
                "INSERT INTO transactions (user_id, description, amount, type, category, timestamp) VALUES (?, ?, ?, ?, ?, ?)", user_id, rule["description"], rule["amount"], rule["type"], rule["category"], transaction_date
            )

            # Update that the rule was already processed this month
            db.execute (
                "UPDATE recurring_transactions SET last_added = ? WHERE id = ?", current_month, rule["id"]
            )
    return


def copy_previous_budgets(user_id):
    """Copy last month's budgets to the actual month"""

    current_month = datetime.now().strftime('%Y-%m')

    current_budgets = db.execute(
        "SELECT id FROM budgets WHERE user_id = ? AND month = ?", user_id, current_month
    )

    if len(current_budgets) > 0:
        return
    
    last_month_recorded = db.execute(
        "SELECT MAX(month) as last_month FROM budgets WHERE user_id = ? AND month < ?", user_id, current_month
    )

    last_month = last_month_recorded[0]["last_month"]

    if last_month:
        db.execute(
            "INSERT INTO budgets (user_id, category_name, amount, month) SELECT user_id, category_name, amount, ? FROM budgets WHERE user_id = ? AND month = ?", current_month, user_id, last_month
        )

@app.context_processor
def inject_conf_var():
    lang = session.get("language", "en")

    return dict(lang=lang, t=translations[lang])


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/set_language/<lang>")
def set_language(lang):
    """Defines app's language"""
    if lang in ["en", "pt"]:
        session["language"] = lang
    return redirect(request.referrer or "/")


@app.route("/")
@login_required
def index():
    """Show user's financial dashboard"""

    # Get user's id from the session
    user_id = session["user_id"]

    copy_previous_budgets(user_id)

    process_recurring_transactions(user_id)

    # Current year and month
    current_year = datetime.now().year
    current_month = datetime.now().month

    # Search user's name for greeting
    username = db.execute("SELECT username FROM users WHERE id = ?", user_id)[0]["username"]

    # Total monthly income
    income_rows = db.execute(
        "SELECT SUM(amount) as total FROM transactions WHERE user_id = ? AND type = 'Income' AND strftime('%m', timestamp) = ? AND strftime('%Y', timestamp) = ?", user_id, str(current_month).zfill(2), str(current_year)
    )
    total_income = income_rows[0]["total"] or 0 # Use 0 if not incomes

    # Total monthly expenses
    expense_rows = db.execute(
      "SELECT SUM(amount) as total FROM transactions WHERE user_id = ? AND type = 'Expense' AND strftime('%m', timestamp) = ? AND strftime('%Y', timestamp) = ?", user_id, str(current_month).zfill(2), str(current_year)
    )
    total_expense = expense_rows[0]["total"] or 0 # Use 0 if not expenses

    # Balance
    balance = total_income - total_expense

    # Last 5 transactions
    recent_transactions = db.execute (
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", user_id
    )

    # Budget's progress
    budget_progress = []
    budgets = db.execute(
        "SELECT category_name, amount FROM budgets WHERE user_id = ? AND month = ?", user_id, f"{current_year}-{str(current_month).zfill(2)}"
    )

    # Get total expense by category
    expenses_by_category = db.execute(
        "SELECT category, SUM(amount) as total FROM transactions WHERE user_id = ? AND type = 'Expense' AND strftime('%Y-%m', timestamp) = ? GROUP BY category", user_id, f"{current_year}-{str(current_month).zfill(2)}"
    )

    # Transform the expenses list into a dictionary for easy search
    spent_map = {item['category']: item['total'] for item in expenses_by_category}

    for budget in budgets:
        category = budget["category_name"]
        spent= spent_map.get(category, 0) # Get the expense or 0, if it doesn't exist
        percentage = (spent / budget["amount"]) * 100 if budget["amount"] > 0 else 0
        budget_progress.append({
            "category": category,
            "budgeted": budget["amount"],
            "spent": spent,
            "percentage": percentage
        })

    return render_template("index.html", username=username, total_income=total_income, total_expense=total_expense, balance=balance, recent_transactions=recent_transactions, budget_progress=budget_progress)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    current_lang = session.get("language", "en")

    # Forget any user_id
    session.clear()

    session["language"] = current_lang

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("error_username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("error_password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid_login", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    current_lang = session.get("language", "en")

    # clear previous session
    session.clear()

    session["language"] = current_lang

    if request.method == "POST":
        # validation of the credentials
        if not request.form.get("username"):
            return apology("missing_username", 400)
        if not request.form.get("password"):
            return apology("missing_password", 400)
        if not request.form.get("confirmation"):
            return apology("missing_confirmation", 400)
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("match_error", 400)

        # search if the user already exists
        rows = db.execute("SELECT * FROM users WHERE username=?", request.form.get("username"))

        if len(rows) != 0:
            return apology("used_username", 400)

        # Register the user
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get(
            "username"), generate_password_hash(request.form.get("password")))

        # Search the updated database
        rows = db.execute("SELECT * FROM users WHERE username=?", request.form.get("username"))

        # Create a new session for the user
        session["user_id"] = rows[0]["id"]

        # Go to the home page now logged in
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    transactions = ["Income", "Expense"]
    categories = db.execute("SELECT * FROM CATEGORIES WHERE user_id IS NULL OR user_id = ?", session["user_id"])

    if request.method == "POST":
        # input of the value and the type of transaction
        amount = request.form.get("amount")
        transaction_type = request.form.get("type")
        description = request.form.get("description")
        category = request.form.get("category")
        lang = session.get("language", "en")

        if not amount:
            return apology("missing_value", 400)
        if not transaction_type:
            return apology("missing_type", 400)
        if not category:
            return apology("missing_category", 400)
        if transaction_type not in ["Income", "Expense"]:
            return apology("invalid_type", 400)

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            return apology("invalid_value", 400)

        db.execute(
            "INSERT INTO transactions (user_id, description, amount, type, category) VALUES (?, ?, ?, ?, ?)", session["user_id"], description, amount, transaction_type,category
        )

        flash(translations[lang]["success_transaction"])
        return redirect("/")
    else:
        return render_template("add.html", transactions=transactions, categories=categories)


@app.route("/delete_transaction", methods=["POST"])
@login_required
def delete_transaction():
    """Delete a user's transactions"""

    transaction_id = request.form.get("transaction_id")
    lang = session.get("language", "en")

    # Delete specific user's transaction
    if transaction_id:
        db.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?", transaction_id, session["user_id"]
        )
        flash(translations[lang]["delete_transaction"])

    return redirect(request.referrer or "/")

@app.route("/history")
@login_required
def history():
    """Show history of transactions with filters"""

    user_id = session["user_id"]

    # Get form's filters (If they exist)
    month_filter = request.args.get("month") #YYYY-MM Format
    category_filter = request.args.get("category")

    # Make the query's beginning
    query = "SELECT * FROM transactions WHERE user_id = ?"

    # Define the values that will take places of the ?
    params = [user_id]

    # Complemente the query based on the filter
    if month_filter:
        query += " AND strftime('%Y-%m', timestamp) = ?"
        params.append(month_filter)

    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)

    # It all is ordered based on the most recents
    query += " ORDER BY timestamp DESC"

    # Execute the final query
    transactions = db.execute(query, *params) # The * is a splat operator

    # Get all the categories for the dropdown list
    categories = db.execute("SELECT name FROM categories WHERE user_id IS NULL OR user_id = ?", user_id)

    return render_template("history.html", transactions=transactions, categories=categories)


@app.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    """Show and manage user's new categories"""

    lang = session.get("language", "en")

    if request.method == "POST":

        # Get user's new category
        new_category = request.form.get("category_name")

        if not new_category:
            return apology("missing_category_name", 400)

        # Verify if category already exists
        existing = db.execute("SELECT * FROM categories WHERE user_id=? AND name=?", session["user_id"], new_category)
        if existing:
            return apology("used_category", 400)

        # Insert the new category
        db.execute("INSERT INTO categories (user_id, name) VALUES (?, ?)", session["user_id"], new_category)

        flash(translations[lang]["added_category"])
        return redirect("/categories")

    else:
        # Get default and user's categories
        user_categories = db.execute("SELECT * FROM categories WHERE user_id IS NULL OR user_id=?", session["user_id"])
        return render_template("categories.html", categories=user_categories)


@app.route("/delete_category", methods = ["POST"])
@login_required
def delete_category():
    """Delete a user's custom category"""

    category_id = request.form.get("category_id")
    lang = session.get("language", "en")


    if category_id:
        db.execute("DELETE FROM categories WHERE id=? AND user_id=?", category_id, session["user_id"])
        flash(translations[lang]["delete_category"])

    return redirect("/categories")


@app.route("/reports")
@login_required
def reports():
    """Show charts of expenses"""

    # Get total of expenses per category on the actual month
    current_month = datetime.now().strftime('%Y-%m') #"2025-10"
    expenses_by_category = db.execute(
        "SELECT category, SUM(amount) as total FROM transactions WHERE user_id = ? AND type = 'Expense' AND strftime('%Y-%m', timestamp) = ? GROUP BY category ORDER BY total DESC", session["user_id"], current_month
    )

    # Prepare data for Chart.js
    labels = []
    data = []
    for row in expenses_by_category:
        labels.append(row["category"])
        data.append(row["total"])

    return render_template("reports.html", labels=labels, data=data)


@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    """Allow user to set monthly budgets for categories"""

    lang = session.get("language", "en")

    if request.method == "POST":
        category = request.form.get("category")
        amount = request.form.get("amount")
        current_month = datetime.now().strftime('%Y-%m')

        # Validation
        if not category or not amount:
            return apology("invalid_budget", 400)
        try:
            amount = float(amount)
            if amount < 0: raise ValueError
        except ValueError:
            return apology("invalid_value", 400)

        # Verify if there already is a budget for this category/month
        existing_budget = db.execute(
            "SELECT id FROM budgets WHERE user_id = ? AND category_name = ? AND month = ?", session["user_id"], category, current_month
        )

        if existing_budget:
            # Update
            db.execute(
                "UPDATE budgets SET amount = ? WHERE id = ?", amount, existing_budget[0]["id"]
            )
        else:
            # Insert
            db.execute(
                "INSERT INTO budgets (user_id, category_name, amount, month) VALUES (?, ?, ?, ?)", session["user_id"], category, amount, current_month
            )

        flash(translations[lang]["save_budget"])
        return redirect("/budget")

    else:
        current_month = datetime.now().strftime('%Y-%m')

        # Get monthly budgets
        budgets = db.execute(
            "SELECT id, category_name, amount FROM budgets WHERE user_id = ? AND month = ?", session["user_id"], current_month
        )
        # Get user's expense categories to the dropdown list
        expense_categories = db.execute(
            "SELECT name FROM categories WHERE (user_id IS NULL OR user_id = ?) AND name != 'Salary'", session["user_id"]
        )

        return render_template("budget.html", budgets=budgets, categories=expense_categories)


@app.route("/delete_budget", methods=["POST"])
@login_required
def delete_budget():
    """Delete a user's budget"""

    budget_id = request.form.get("budget_id")
    lang = session.get("language", "en")


    # Delete in the database
    if budget_id:
        db.execute(
            "DELETE FROM budgets WHERE id = ? AND user_id = ?", budget_id, session["user_id"]
        )
        flash(translations[lang]["delete_budget"])

    return redirect("/budget")


@app.route("/recurring", methods=["GET", "POST"])
@login_required
def recurring():
    """Manage recurring transactions"""

    user_id = session["user_id"]
    transactions = ["Income", "Expense"]
    lang = session.get("language", "en")


    if request.method == "POST":
        amount = request.form.get("amount")
        transaction_type = request.form.get("type")
        description = request.form.get("description")
        category = request.form.get("category")
        day = request.form.get("day_of_month")

        # Validation
        if not all([amount, transaction_type, description, category, day]):
            return apology("missing_recurring", 400)
        try:
            amount = float(amount)
            day = int(day)
            if amount <= 0 or not (1 <= day <= 31):
                raise ValueError
        except ValueError:
            return apology("invalid_recurring", 400)

        # Insert the new rule in db
        db.execute(
            "INSERT INTO recurring_transactions (user_id, description, amount, type, category, day_of_month) VALUES (?, ?, ?, ?, ?, ?)", user_id, description, amount, transaction_type, category, day
        )

        flash(translations[lang]["save_recurring"])

        return redirect("/recurring")

    else:
        recurring_trans = db.execute(
            "SELECT * FROM recurring_transactions WHERE user_id = ?", user_id
        )
        categories = db.execute (
            "SELECT name FROM categories WHERE user_id IS NULL OR user_id = ?", user_id
        )

        return render_template("recurring.html", recurring_trans=recurring_trans, categories=categories, transactions=transactions)


@app.route("/delete_recurring", methods=["POST"])
@login_required
def delete_recurring():
    """Delete a user's recurring transaction rule"""

    recurring_id = request.form.get("recurring_id")
    lang = session.get("language", "en")

    if recurring_id:
        db.execute(
            "DELETE FROM recurring_transactions WHERE id = ? AND user_id = ?", recurring_id, session["user_id"]
        )
        flash(translations[lang]["delete_recurring"])

    return redirect("/recurring")


if __name__ == "__main__":
    app.run()
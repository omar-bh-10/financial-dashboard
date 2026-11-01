import os
import uuid
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Use non-GUI backend for server
import matplotlib.pyplot as plt

# -----------------------------
# Flask configuration
# -----------------------------
app = Flask(__name__)
app.secret_key = "super-secret-key"  # For flash messages (change in production)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
CHART_FOLDER = os.path.join(BASE_DIR, "static", "charts")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CHART_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"xlsx"}


def allowed_file(filename: str) -> bool:
    """
    Check if the uploaded file has an allowed extension.
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# -----------------------------
# Chart generation helpers
# -----------------------------
def generate_line_chart(df: pd.DataFrame, chart_id: str) -> str:
    """
    Generate a line chart of transactions over time.
    """
    # Sort by date to ensure proper line chart
    df_sorted = df.sort_values("Date")

    plt.figure(figsize=(8, 4))
    plt.plot(df_sorted["Date"], df_sorted["Amount"], marker="o", linestyle="-", color="#1f77b4")
    plt.title("Transactions Over Time")
    plt.xlabel("Date")
    plt.ylabel("Amount")
    plt.grid(True, alpha=0.3)

    filename = f"line_{chart_id}.png"
    filepath = os.path.join(CHART_FOLDER, filename)
    plt.tight_layout()
    plt.savefig(filepath, transparent=True)
    plt.close()

    return filename


def generate_expense_pie_chart(df: pd.DataFrame, chart_id: str) -> str:
    """
    Generate a pie chart of expenses grouped by description.
    Only negative amounts are considered expenses.
    """
    expenses = df[df["Amount"] < 0].copy()

    if expenses.empty:
        # No expenses, create an empty chart
        plt.figure(figsize=(6, 6))
        plt.text(0.5, 0.5, "No expenses data", ha="center", va="center", fontsize=14)
        plt.axis("off")
    else:
        # Group expenses by description
        grouped = expenses.groupby("Description")["Amount"].sum().abs()

        plt.figure(figsize=(6, 6))
        plt.pie(
            grouped,
            labels=grouped.index,
            autopct="%1.1f%%",
            startangle=140,
            pctdistance=0.85,
        )
        plt.title("Expenses Breakdown")

        # Draw circle for donut style
        centre_circle = plt.Circle((0, 0), 0.60, fc="white")
        fig = plt.gcf()
        fig.gca().add_artist(centre_circle)

    filename = f"pie_{chart_id}.png"
    filepath = os.path.join(CHART_FOLDER, filename)
    plt.tight_layout()
    plt.savefig(filepath, transparent=True)
    plt.close()

    return filename


def generate_bar_chart(df: pd.DataFrame, chart_id: str) -> str:
    """
    Generate a bar chart comparing total revenues vs total expenses.
    Revenues: positive amounts
    Expenses: negative amounts (absolute value).
    """
    revenues = df[df["Amount"] > 0]["Amount"].sum()
    expenses = df[df["Amount"] < 0]["Amount"].sum()

    total_revenue = revenues
    total_expense = abs(expenses)

    categories = ["Revenue", "Expenses"]
    values = [total_revenue, total_expense]
    colors = ["#2ecc71", "#e74c3c"]

    plt.figure(figsize=(6, 4))
    plt.bar(categories, values, color=colors)
    plt.title("Revenue vs Expenses")
    plt.ylabel("Amount")
    plt.grid(axis="y", alpha=0.3)

    filename = f"bar_{chart_id}.png"
    filepath = os.path.join(CHART_FOLDER, filename)
    plt.tight_layout()
    plt.savefig(filepath, transparent=True)
    plt.close()

    return filename


# -----------------------------
# Data analysis helper
# -----------------------------
def analyze_transactions(df: pd.DataFrame) -> dict:
    """
    Compute financial KPIs from the transactions DataFrame.
    Expected columns: Date, Description, Amount
    """
    # Ensure correct dtypes
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")

    # Drop rows with invalid data
    df = df.dropna(subset=["Date", "Amount"])

    total_revenue = df[df["Amount"] > 0]["Amount"].sum()
    total_expenses = df[df["Amount"] < 0]["Amount"].sum()
    current_balance = df["Amount"].sum()
    num_transactions = len(df)

    # Highest expense (most negative)
    highest_expense_row = df[df["Amount"] < 0].sort_values("Amount").head(1)
    highest_expense = (
        float(highest_expense_row["Amount"].iloc[0])
        if not highest_expense_row.empty
        else 0.0
    )
    highest_expense_desc = (
        highest_expense_row["Description"].iloc[0]
        if not highest_expense_row.empty
        else "N/A"
    )

    # Highest revenue (largest positive)
    highest_revenue_row = df[df["Amount"] > 0].sort_values("Amount", ascending=False).head(1)
    highest_revenue = (
        float(highest_revenue_row["Amount"].iloc[0])
        if not highest_revenue_row.empty
        else 0.0
    )
    highest_revenue_desc = (
        highest_revenue_row["Description"].iloc[0]
        if not highest_revenue_row.empty
        else "N/A"
    )

    return {
        "total_revenue": float(total_revenue),
        "total_expenses": float(abs(total_expenses)),
        "current_balance": float(current_balance),
        "num_transactions": int(num_transactions),
        "highest_expense": float(highest_expense),
        "highest_expense_desc": highest_expense_desc,
        "highest_revenue": float(highest_revenue),
        "highest_revenue_desc": highest_revenue_desc,
        "df": df,  # return cleaned df for charts
    }


# -----------------------------
# Routes
# -----------------------------
@app.route("/", methods=["GET"])
def index():
    """
    Render the main dashboard page.
    Initially, no data is displayed until a file is uploaded.
    """
    return render_template("index.html", data=None, charts=None)


@app.route("/upload", methods=["POST"])
def upload_file():
    """
    Handle file upload, validation, analysis, and chart generation.
    """
    if "file" not in request.files:
        flash("No file part in the request.", "error")
        return redirect(url_for("index"))

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("Invalid file type. Please upload a .xlsx file.", "error")
        return redirect(url_for("index"))

    try:
        # Secure filename and save temporarily
        filename = secure_filename(file.filename)
        unique_id = uuid.uuid4().hex
        saved_filename = f"{unique_id}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, saved_filename)
        file.save(filepath)

        # Read Excel using pandas + openpyxl
        df = pd.read_excel(filepath, engine="openpyxl")

        # Basic validation of required columns
        required_columns = {"Date", "Description", "Amount"}
        if not required_columns.issubset(df.columns):
            flash(
                "Invalid file format. The Excel file must contain columns: Date, Description, Amount.",
                "error",
            )
            return redirect(url_for("index"))

        # Analyze data
        analysis = analyze_transactions(df)

        # Generate charts
        line_chart = generate_line_chart(analysis["df"], unique_id)
        pie_chart = generate_expense_pie_chart(analysis["df"], unique_id)
        bar_chart = generate_bar_chart(analysis["df"], unique_id)

        charts = {
            "line_chart": line_chart,
            "pie_chart": pie_chart,
            "bar_chart": bar_chart,
        }

        # Optionally remove uploaded file after processing
        try:
            os.remove(filepath)
        except OSError:
            pass

        return render_template("index.html", data=analysis, charts=charts)

    except Exception as e:
        # Log error in real app; here we just flash it
        flash(f"An error occurred while processing the file: {str(e)}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    # Run in debug mode for development
    app.run(debug=True)

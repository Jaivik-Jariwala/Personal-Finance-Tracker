# Personal Finance Tracker

## Overview

The Personal Finance Tracker is a web application designed to help users manage their investments, properties, and financial health. Built with Flask and SQLite, it provides a user-friendly interface to track assets, calculate future values, and export data to Excel.

## Features

* **Investment Tracking:** Manage investments across multiple categories and family members.
* **Property Management:** Record property values and rental income.
* **Future Value Calculation:** Estimate future net worth based on user-defined growth rates and timelines.
* **Excel Export:** Download financial summaries in Excel format.
* **Responsive Design:** Accessible on both desktop and mobile devices.

## Installation

1. **Clone the Repository:**

   ```bash
   git clone <repository-url>
   cd Personal-Finance-Tracker
   ```
2. **Set Up a Virtual Environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```
4. **Set Up the Runtime Environment:**

   * Navigate to the `runtime` directory:
     ```bash
     cd runtime
     ```
   * Activate the virtual environment:
     ```bash
     source venv/bin/activate  # On Windows: venv\Scripts\activate
     ```
5. **Run the Application:**

   * Navigate to the `dist` directory:
     ```bash
     cd ../dist
     ```
   * Execute the application:
     ```bash
     ./app.exe  # On Windows: app.exe
     ```

   The app will launch in a PyWebView window.

## Usage

* **Add Categories and Members:** Use the management section to add new investment categories or family members.
* **Input Data:** Enter current values for investments and properties.
* **View Summaries:** Check total assets, liabilities, net worth, and future projections.
* **Export Data:** Download your financial data as an Excel file.

## Dependencies

* Flask
* Flask-SQLAlchemy
* Pandas
* PyWebView
* AppDirs

## File Structure

* `app.py`: Main Flask application with API endpoints and database logic.
* `static/index.html`: Frontend interface for the application.
* `finance.db`: SQLite database storing financial data.
* `log.txt`: Log file for application events.
* `dist/app.exe`: Executable file to run the application.
* `runtime/venv`: Virtual environment for runtime dependencies.

## Notes

* Ensure the database (`finance.db`) is created in the user data directory upon first run.
* The application uses threading for database operations to prevent blocking.
* Logs are written to `log.txt` for debugging and monitoring.

## License

This project is licensed under the MIT License.

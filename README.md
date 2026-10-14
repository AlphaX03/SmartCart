
# SmartCart — Grocery Billing & Inventory Management System

SmartCart is a web-based grocery billing and inventory management application built with Flask and MySQL. It helps grocery store owners manage products, process bills, monitor sales, view reports, and configure store settings through a centralized dashboard.

## Features

- **User Authentication:** Store owners can register and log in.
- **Multi-Store Support:** Each registered store has its own account and store-specific data.
- **Dashboard:** View store-related sales and inventory information.
- **Product Management:** Add, view, edit, and delete products.
- **Billing:** Generate bills with product quantities, prices, and totals.
- **Inventory Management:** Update stock quantities when bills are generated.
- **Billing History:** Review previous bills and payment information.
- **Sales:** View sales-related information.
- **Reports:** Access sales and inventory reporting features.
- **Store Settings:** Manage store details and configuration.
- **Receipt Generation:** Display and print bill receipts with store information.

## Technology Stack

- **Frontend:** HTML, CSS, JavaScript, Bootstrap
- **Backend:** Python, Flask
- **Database:** MySQL
- **Templating:** Jinja2
- **Version Control:** Git and GitHub

## Project Structure

```text
SmartCart/
├── app.py
├── requirements.txt
├── .gitignore
├── README.md
├── templates/
└── static/
```

## Getting Started

### Prerequisites

Install the following software:

- Python
- MySQL Server
- Git (optional, for version control)

### 1. Clone the repository

```bash
git clone https://github.com/AlphaX03/SmartCart.git
cd SmartCart
```


### 2. Create and activate a virtual environment

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file in the project root. Configure the variables required by `app.py`, including the Flask secret key and MySQL connection settings.

Do not commit `.env` or publish database passwords and secret keys.

### 5. Prepare the MySQL database

Create the required MySQL database and tables using the project's database schema or setup instructions. Configure the database connection details in your local environment.

Do not import a private development database backup into a shared environment.

### 6. Run the application

```bash
python app.py
```

Open the local address shown in the terminal, typically:

http://127.0.0.1:5000/

## Current Limitations and Planned Improvements

SmartCart is a working development prototype. The following work remains planned or incomplete:

- Customer management.
- Integration with a real online payment gateway and payment verification.
- Comprehensive security testing and production hardening.
- Production deployment and operational monitoring.
- Additional testing of multi-store data isolation and edge cases.

Online payment status currently does not mean that a real payment has been verified by a payment provider.

## Project Status

**Status:** Active development

SmartCart is being developed to simplify grocery store billing, product inventory management, and store-level reporting.

## Contributing

Suggestions and feedback are welcome. Test changes carefully before using the application with real business data.

## License

No open-source license has been selected yet. All rights are reserved by the project owner unless a license is added.

# NIT Trichy Order-to-Audit Management System
**Enterprise Foundation, Manufacturing Execution & Auditing Platform**

This repository contains the complete industrial-grade **Order-to-Audit Management System** for the **NIT Trichy Order-to-Audit Problem Statement**. Engineered using **Django 6.x**, **PostgreSQL** (with zero-setup SQLite fallback), pure-Python audit PDF generation, and a modern, responsive **Bootstrap 5** user interface.

The platform enforces end-to-end relational auditability across the entire enterprise lifecycle:
$$\text{Supplier Purchase} \longrightarrow \text{Stock Ledger} \longrightarrow \text{BOM Production} \longrightarrow \text{Sales Order} \longrightarrow \text{Dual GST Invoice} \longrightarrow \text{Dispatches} \longrightarrow \text{Payment Settlement} \longrightarrow \text{Audit Trail}$$

---

## 1. Role-Based Access Control (RBAC) Architecture

The platform enforces strict view-level and service-level governance for six distinct enterprise personas:

| Role | Code | Responsibility in Order-to-Audit Lifecycle | Dedicated Workspace / Route |
| :--- | :--- | :--- | :--- |
| **Administrator** | `ADMIN` | System security, user account provisioning, RBAC management, technical configuration, sales approvals. | `/dashboard/admin/` |
| **Salesman** | `SALESMAN` | Customer quotes, sales order ingestion, delivery destination mapping, order pipeline tracking. | `/dashboard/sales/` |
| **Production** | `PRODUCTION` | Shop floor control, BOM recipe execution, yield/consumption variance recording, lot issuance. | `/dashboard/production/` |
| **Auditor** | `AUDITOR` | End-to-end audit traceability, price & invoice variance, immutable log inspection, compliance review. | `/dashboard/auditor/` |
| **Owner** | `OWNER` | Executive leadership, revenue analytics, real-time KPI overview, financial health, final approvals. | `/dashboard/owner/` |
| **Accountant** | `ACCOUNTANT` | Accounts receivable, customer aging, payment collection vouchers, GST register reconciliation. | `/finance/` |

---

## 2. Modular Project Structure

The project is structured into eight decoupled, single-responsibility Django applications:

```text
NIT/
├── manage.py                          # Django CLI utility
├── requirements.txt                   # Production dependencies (Django, psycopg2, whitenoise, etc.)
├── Procfile                           # Production WSGI release & worker specification (Heroku/Render)
├── Dockerfile                         # Production multi-stage container build definition
├── docker-compose.yml                 # Multi-container orchestration (PostgreSQL + Django + WhiteNoise)
├── .env.example                       # Production & development environment variable template
├── .gitignore                         # Comprehensive version control ignore rules
├── README.md                          # Master documentation & benchmark audit report
├── nit_system/                        # Root Django configuration package
│   ├── __init__.py
│   ├── settings.py                    # 12-factor configuration, security headers, WhiteNoise & DATABASE_URL
│   ├── urls.py                        # Central URL dispatcher & custom error handlers (403, 404, 500)
│   ├── wsgi.py                        # WSGI entry point for Gunicorn
│   └── asgi.py                        # ASGI entry point
├── apps/                              # Enterprise Django applications
│   ├── accounts/                      # Custom user authentication, 6 roles, dual email/username backend
│   ├── core/                          # Base layout, institutional landing, and Centralized Immutable Audit Trail
│   ├── dashboard/                     # Central role dispatcher & Executive Owner Dashboard with real KPIs
│   ├── master_data/                   # Customers, Suppliers, Raw Materials, Packaging, SKUs, and BOM recipes
│   ├── inventory/                     # Ledger-based inventory, Purchase Orders, GRN receipts, and Stock Adjustments
│   ├── production/                    # BOM-based work orders, actual consumption, yield variance, and batch costing
│   ├── sales/                         # Sales orders, Admin approvals, negative stock guard, pure-Python PDF tax invoice
│   └── finance/                       # Accounts receivable, payment vouchers, overpayment guard, and GST reports
├── static/                            # Static CSS and JavaScript assets
└── templates/                         # Modular Bootstrap 5 HTML templates
```

---

## 3. NIT Trichy South Indian Snacks Benchmark Specifications

The platform is engineered and verified against the **exact South Indian snacks problem statement benchmark**:

### Benchmark Invariant Overview

```
[Opening Stock]
  Flour: 100 kg @ ₹42/kg | Oil: 30 L @ ₹140/L | Spice mix: 5 kg @ ₹200/kg
  Pouches: 500 pcs @ ₹2.50/ea | Cartons: 30 pcs @ ₹15/ea (holds 20 pkts)
  Finished Murukku 200g: 50 pkts (Selling price: ₹50.00 before 5% GST, MRP: ₹52.50)
         │
         ▼
[Purchase Order & Inward Consignment (GRN)]
  Flour Purchase: 60 kg @ ₹45.00/kg
  Pre-Production Stock on Hand: 100 kg + 60 kg = 160.00 kg
         │
         ▼
[Production Batch Execution (BOM: BOM-MRK-200PKT)]
  Planned Batch: 200 packets
  Actual Good Output: 188 packets (Yield Variance: -6.00% -> ALERT TRIGGERED)
  Actual Consumptions:
    - Flour: 40.0 kg (Closing: 120.0 kg, Variance: 0.00%)
    - Oil: 10.5 L (Closing: 19.5 L, Variance: +5.00% -> ALERT TRIGGERED)
    - Spice mix: 1.2 kg (Closing: 3.8 kg, Variance: 0.00%)
    - Pouches: 194 pcs (188 good + 6 damaged, Closing: 306 pcs)
    - Cartons: 9 pcs (Closing: 21 pcs)
  Costing: Materials ₹4,055 + Labour ₹1,200 + Gas/Power ₹600 = Total ₹5,855.00 (₹31.14 / pkt)
  Finished Murukku Stock: 50 opening + 188 produced = 238.00 packets
         │
         ├────────────────────────────────────────┐
         ▼                                        ▼
[Scenario 1: Retailer A (Tamil Nadu)]      [Scenario 2: Distributor B (Karnataka)]
  - Intra-State 5% GST (2.5% CGST + SGST)   - Inter-State 5% IGST
  - Order: 150 pkts @ ₹50.00                - Order: 120 pkts requested
  - Taxable Value: ₹7,500.00                - Available Stock: 88.00 pkts
  - CGST: ₹187.50 | SGST: ₹187.50           - Stock Shortage: Exactly 32.00 pkts
  - Total Invoice: ₹7,875.00                - Approval / Dispatch: STRICTLY BLOCKED
  - Dispatched: 150 packets                 - Negative inventory prevented
  - Closing Finished Stock: 88.00 pkts      - Full Invoice: ₹6,000 + 5% IGST (₹300) = ₹6,300
  - Payment Received: ₹4,000.00 (UPI)
  - Balance Outstanding: ₹3,875.00 (PARTIAL)
```

---

## 4. Benchmark Verification Table

| Parameter | Opening Stock | Purchase (GRN) | Production Issue / Output | Dispatch Issue | Benchmark Closing Balance | Benchmark Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Flour (`RM-FLOUR`)** | 100.0 kg @ ₹42/kg | +60.0 kg @ ₹45/kg | -40.0 kg | - | **120.00 kg** | Verified ($\Delta = 0$) |
| **Oil (`RM-OIL`)** | 30.0 L @ ₹140/L | - | -10.5 L | - | **19.50 L** | Verified (+5% alert triggered) |
| **Spice Mix (`RM-SPICE`)** | 5.0 kg @ ₹200/kg | - | -1.2 kg | - | **3.80 kg** | Verified ($\Delta = 0$) |
| **Pouches (`PM-POUCH`)** | 500 pcs @ ₹2.50/ea | - | -194 pcs (188 good + 6 damaged) | - | **306 pcs** | Verified ($\Delta = 0$) |
| **Cartons (`PM-CARTON`)** | 30 pcs @ ₹15/ea | - | -9 pcs | - | **21 pcs** | Verified ($\Delta = 0$) |
| **Finished Murukku 200g** | 50 pkts | - | +188 good pkts | -150 pkts (Retailer A) | **88 pkts** | Verified (Shortage: 32 on 120 req) |
| **Retailer A Invoice** | - | - | - | 150 pkts @ ₹50 | **₹7,875.00** | Verified (CGST ₹187.50, SGST ₹187.50) |
| **Retailer A Payment** | - | - | - | ₹4,000 received | **₹3,875.00** | Verified (Status: `PARTIAL`) |
| **Distributor B Order** | - | - | - | 120 pkts req | **32 pkts Shortage** | Verified (Approval blocked) |

---

## 5. System Highlights & Technical Innovations

### 1. Centralized Immutable System Audit Trail (`apps/core`)
- Records every critical operational event across the platform: master data changes, purchase orders, goods receipts, stock adjustments, production work orders, sales approvals, dispatches, and payments.
- **Strict Immutability Guarantee**: Model-level `save()` and `delete()` methods raise `ValidationError` on modifications. Django Admin delete/change permissions are completely disabled. Bulk updates and deletions raise validation errors.
- Filterable by module, user, date range, and severity.

### 2. Executive Owner Dashboard (`apps/dashboard`)
- Real-time aggregated KPIs driven directly by live SQL queries (zero hardcoded values): Total Invoiced Turnover, Collected Revenue, Outstanding Receivables, Total Production Volume, Finished Goods Inventory, Low-Stock Alerts, and Active Variance Alerts.
- Visual breakdown of Recent Invoices, Pending Sales Orders Requiring Approval, Dispatches, and Payments.

### 3. Pure-Python PDF 1.4 Tax Invoice Generator (`apps/sales`)
- Generates official, downloadable **GST Tax Invoices** complying with Section 31 of the CGST Act.
- Built without external C-libraries (zero pip dependencies) using a custom PDF 1.4 binary stream writer.
- Embeds seller snapshot (NIT Trichy, GSTIN: `33NITTRICHY1Z5 (Demo Placeholder)`), buyer billing/shipping details, HSN codes, and itemized CGST/SGST/IGST tax breakdowns.

### 4. Zero-Dependency RFC 4180 CSV & Excel 2003 XML Exports (`apps/finance`)
- Pure-Python data export engine streaming standard CSV files with UTF-8 BOM (`\ufeff`) for Microsoft Excel and Google Sheets.
- Generates native Microsoft Excel Spreadsheet 2003 XML (`.xls`) workbooks with formatted headers, decimal styling, and multi-sheet support without requiring heavy third-party libraries (`openpyxl` or `xlsxwriter`).

---

## 6. Demonstration Credentials

All accounts are pre-seeded for fast evaluation (Default Password for all: `nit@12345`):

| Role | Email | Username | Default Password | Workspace Route |
| :--- | :--- | :--- | :--- | :--- |
| **Administrator** | `admin@nit.edu` | `admin` | `nit@12345` | `/dashboard/admin/` |
| **Salesman** | `salesman@nit.edu` | `salesman` | `nit@12345` | `/dashboard/sales/` |
| **Production** | `production@nit.edu` | `production` | `nit@12345` | `/dashboard/production/` |
| **Auditor** | `auditor@nit.edu` | `auditor` | `nit@12345` | `/dashboard/auditor/` |
| **Owner** | `owner@nit.edu` | `owner` | `nit@12345` | `/dashboard/owner/` |
| **Accountant** | `accountant@nit.edu` | `accountant` | `nit@12345` | `/finance/` |

> **Convenience Feature**: On the sign-in screen (`/accounts/login/`), one-click role buttons automatically populate credentials for immediate demonstration.

---

## 7. Quick Start & Local Execution

### 1. Prerequisites
- Python 3.11, 3.12, or 3.13
- Git

### 2. Clone Repository & Setup Virtual Environment
```bash
git clone <repository_url>
cd NIT
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Database Setup & Migrations
The system defaults to zero-setup SQLite (`USE_SQLITE=True`). To use PostgreSQL, set `USE_SQLITE=False` and provide `DATABASE_URL` or `DB_*` variables in `.env`.
```bash
python manage.py migrate
```

### 5. Seed Test Users & Execute Benchmarks
```bash
# Seed 6 institutional staff accounts
python manage.py seed_users

# Seed exact NIT South Indian snacks benchmark opening inventory & BOM
python manage.py seed_snacks_benchmark

# Run production benchmark (188 pkts output, 3% alerts, closing balances)
python manage.py run_nit_production_benchmark

# Run sales benchmark (Retailer A 150 pkts, Distributor B 32 shortage, payments)
python manage.py run_nit_sales_benchmark
```

### 6. Run the Enterprise Automated Test Suite (89 Tests)
```bash
python manage.py test apps.accounts apps.core apps.dashboard apps.master_data apps.inventory apps.production apps.sales apps.finance
```
*(All 89 tests pass across all 8 modules).*

### 7. Launch Local Server
```bash
python manage.py runserver
```
Visit `http://127.0.0.1:8000/` in your web browser.

---

## 8. Containerized Deployment with Docker & Docker Compose

Deploy the entire platform with PostgreSQL in a single command:

```bash
# Build images and start PostgreSQL + Django application
docker-compose up --build -d

# Check service logs
docker-compose logs -f web

# Stop services and preserve data
docker-compose down
```

The Docker Compose configuration:
1. Provisions PostgreSQL 16 on alpine with automated health checks.
2. Applies all Django database migrations automatically.
3. Seeds all 6 test accounts.
4. Executes the complete NIT Trichy snacks benchmark sequence.
5. Launches the Gunicorn WSGI server on `http://localhost:8000/`.

---

## 9. Production Cloud Deployment Guide

The platform is designed according to **12-Factor App principles** and includes complete support for cloud hosts such as **Render**, **Railway**, **Heroku**, or custom **Ubuntu/Debian VPS**:

### Environment Variables for Production
Configure the following environment variables in your hosting dashboard:

| Variable | Recommended Production Value | Description |
| :--- | :--- | :--- |
| `DEBUG` | `False` | Disables verbose debug tracebacks. |
| `SECRET_KEY` | *(50+ character random string)* | Cryptographic signing key. |
| `ALLOWED_HOSTS` | `your-app.onrender.com,your-domain.com` | Allowed incoming HTTP Host headers. |
| `CSRF_TRUSTED_ORIGINS` | `https://your-app.onrender.com` | Trusted origins for CSRF validation. |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/dbname` | Full PostgreSQL connection URL. |
| `USE_SQLITE` | `False` | Disables SQLite and connects to PostgreSQL. |
| `SECURE_SSL_REDIRECT` | `True` | Enforces HTTPS redirection. |
| `SESSION_COOKIE_SECURE`| `True` | Transmits session cookies only over HTTPS. |
| `CSRF_COOKIE_SECURE` | `True` | Transmits CSRF cookies only over HTTPS. |

### Build & Release Commands
- **Build Command**: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- **Release Command** (in `Procfile`): `python manage.py migrate --noinput`
- **Start Command** (in `Procfile`): `gunicorn nit_system.wsgi:application --bind 0.0.0.0:$PORT`

### Deployment Verification
Run the automated deployment readiness check:
```bash
python manage.py check --deploy
```
*(Identifies 0 issues when `DEBUG=False` and production settings are configured).*

---

## 10. Educational & Academic Demonstration Notice

- **Demo Seller GSTIN**: `33NITTRICHY1Z5 (Demo Placeholder)` is clearly marked throughout all invoices, dispatches, and reports as an academic simulation identifier, not an official registered commercial GSTIN.
- **Auditing Integrity**: All financial computations, tax breakdowns, and variance alerts adhere to Indian GST guidelines and cost accounting standards for educational evaluation purposes.

# ManuFlow — Manufacturing Execution & ERP Platform

ManuFlow is an enterprise-grade manufacturing execution system (MES) and resource planning (ERP) platform built with **Django 6.x**, **PostgreSQL** (with zero-setup SQLite fallback for local development), and a responsive **Bootstrap 5** user interface.

The platform orchestrates an end-to-end, relationally auditable manufacturing lifecycle: from supplier procurement and recipe-driven production to dual-tax GST sales invoicing, dispatches, receivables reconciliation, and an immutable audit trail.

---

## 1. Enterprise Architecture & Operational Problem Statement

### Operational Benchmark Reference
ManuFlow is benchmarked against rigorous food manufacturing standards, modeling the production, inventory ledger, and dual-tax accounting requirements of a commercial South Indian snacks manufacturing enterprise. Reference benchmark specifications, standard opening balances, and verification figures provide verifiable ground truth for enterprise compliance, auditing, and operational demonstration.

### Problem Statement
Small and medium manufacturing enterprises frequently struggle with disjointed operational records:
* Material consumption is rarely reconciled against recipe standards in real time.
* Finished goods inventory can slip into negative balances when dispatches precede stock updates.
* Tax invoicing often lacks direct traceability to physical dispatch challans.
* Financial receivables reconciliation across partial payments and credit terms is prone to manual error.
* Transaction audit logs are vulnerable to unauthorized edits or deletions.

ManuFlow solves these problems through strict relational constraints, automated inventory ledgers, dynamic variance alerts, and application-level audit immutability.

---

## 2. Project Objectives

1. **Deterministic Inventory Ledger**: Enforce a double-entry style stock ledger where all additions, issues, and adjustments are recorded as discrete, traceable movement entries. Negative stock is strictly prevented.
2. **Recipe-Driven Production (BOM)**: Compute planned versus actual consumption of raw materials and packaging items, triggering automatic variance alerts when actual yield deviates by more than 3% from BOM specifications.
3. **Role-Based Access Control (RBAC)**: Enforce strict separation of duties across six operational personas with custom dashboards and route-level authorization.
4. **Statutory Tax Invoicing Simulation**: Calculate dual-tax GST breakdowns (Intra-state CGST + SGST vs. Inter-state IGST) with pure-Python PDF 1.4 tax invoice generation.
5. **Payment Settlement & Receivables**: Track customer credit balances, support partial and full settlement vouchers across multiple modes (UPI, Cash, NEFT, RTGS, Cheque), and reject overpayments.
6. **Application-Level Immutable Audit Trail**: Record all critical actions with before/after state diffs, blocking deletion or modification of audit records within the application layer.

---

## 3. Role-Based Access Control (RBAC)

The application implements six distinct user roles with dedicated workspaces and route-level permission checks:

| Role | System Code | Scope & Responsibilities | Workspace Route |
| :--- | :--- | :--- | :--- |
| **Administrator** | `ADMIN` | User account provisioning, role assignment, system settings, and sales order approvals. | `/dashboard/admin/` |
| **Salesman** | `SALESMAN` | Customer registration, sales order creation, dispatch tracking, and order status review. | `/dashboard/sales/` |
| **Production Manager** | `PRODUCTION` | Work order scheduling, batch execution, material consumption, and yield variance review. | `/dashboard/production/` |
| **Compliance Auditor** | `AUDITOR` | End-to-end verification, price and tax reconciliation, and immutable audit trail review. | `/dashboard/auditor/` |
| **Business Owner** | `OWNER` | Executive KPI oversight, revenue analytics, inventory valuation, and final approvals. | `/dashboard/owner/` |
| **Accountant** | `ACCOUNTANT` | Accounts receivable, customer aging, payment collection vouchers, and GST reports. | `/finance/` |

---

## 4. Key Implemented Modules

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ManuFlow Architecture                             │
└─────────────────────────────────────────────────────────────────────────────┘
  [Master Data]  ──► [Procurement & Inventory] ──► [Production & BOM Execution]
        │                      │                                 │
        ▼                      ▼                                 ▼
  [Sales Orders] ──► [Dual GST Tax Invoicing]  ──► [Dispatches & Payments]
                               │
                               ▼
        [Financial Reports & Central Immutable Audit Trail]
```

### 1. Master Data Management (`apps/master_data`)
* Products, Pack Sizes, and SKUs with configurable pricing and HSN codes.
* Customer directory (Retailers and Distributors) with GSTIN and billing/shipping addresses.
* Supplier management with contact details and terms.
* Raw and packaging material catalogs with reorder points and default valuation rates.
* Units of Measure (UOM) with decimal conversion factors.
* Bill of Materials (BOM) multi-item recipes with scrap tolerances.

### 2. Inventory & Procurement (`apps/inventory`)
* Purchase Orders (PO) with multi-item entry and supplier assignment.
* Goods Receipt Notes (GRN) that post verified incoming quantities directly to the stock ledger.
* Real-time stock summary with low-stock threshold warnings.
* Immutable stock movement ledger detailing opening, received, issued, and closing balances.
* Physical stock adjustment vouchers with supervisor approval workflows.

### 3. Production & Batch Execution (`apps/production`)
* Work order creation mapped to active BOM recipes and target output quantities.
* Batch execution recording actual raw material and packaging usage against planned norms.
* Automatic variance calculation with visual alerts when yield or material usage deviates by >3%.
* Comprehensive batch costing calculating material, direct labour, overhead, and unit cost per packet.
* Automatic stock ledger posting: issues raw materials and adds finished goods upon completion.

### 4. Sales & GST Invoicing (`apps/sales`)
* Sales order entry with live stock availability verification.
* Guard against negative inventory: orders exceeding available finished stock are blocked from approval.
* Automated tax calculation:
  * **Intra-State**: 2.5% CGST + 2.5% SGST (for buyers in same state).
  * **Inter-State**: 5.0% IGST (for out-of-state buyers).
* **Pure-Python PDF 1.4 Tax Invoice Generator**: Generates formatted, downloadable PDF tax invoices without external C-library dependencies (`weasyprint` or `reportlab`).
* Dispatch challan recording linked directly to invoice numbers and finished stock deductions.

### 5. Finance, Receivables & Reports (`apps/finance`)
* Accounts receivable aging and customer-wise outstanding balances.
* Payment recording vouchers supporting UPI, Cash, NEFT, RTGS, and Cheque.
* Strict transactional overpayment protection preventing payments beyond the outstanding balance.
* Monthly GST summary and sales registers with intra/inter-state segregation.
* Production variance, consumption, and dispatch audit reports.
* **Data Exports**: Pure-Python RFC 4180 CSV and native Excel 2003 XML (`.xls`) spreadsheet exports.

### 6. Centralized Audit Trail (`apps/core`)
* Application-level immutable audit logging capturing user, action, module, object reference, timestamp, and JSON before/after state payloads.
* Model-level guards (`save()` and `delete()` exceptions) and Django Admin permission revocation prevent tampering with audit records.

---

## 5. Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | Python 3.12 / Django 6.1.2 | Core application logic, ORM, authentication, and routing |
| **Database (Production)** | Neon Serverless PostgreSQL | Scalable cloud PostgreSQL with SSL encryption |
| **Database (Development)**| SQLite 3 | Zero-configuration local database engine |
| **WSGI Server** | Gunicorn 23.0.0 | Production HTTP process management |
| **Static File Hosting** | WhiteNoise 6.9.0 | High-performance static asset compression and caching |
| **Database Abstraction** | dj-database-url 2.3.0 | 12-factor `DATABASE_URL` parsing with SSL mode support |
| **Frontend Framework** | Bootstrap 5.3.3 | Responsive grid, accessible forms, and UI components |
| **Iconography** | Bootstrap Icons 1.11.3 | Scalable vector interface icons |
| **Document Generation** | Pure-Python PDF 1.4 Writer | Lightweight PDF generation without external binaries |

---

## 6. Project Folder Structure

```text
ManuFlow/
├── manage.py                          # Django CLI management utility
├── requirements.txt                   # Production dependencies with locked versions
├── requirements.lock                  # Deterministic dependency manifest
├── build.sh                           # Production build script for Linux/Render
├── render.yaml                        # Render Blueprint specification (Web Service)
├── Procfile                           # Process file for PaaS deployments
├── Dockerfile                         # Container build definition
├── docker-compose.yml                 # Local multi-container development configuration
├── .gitattributes                     # Enforces LF line endings for shell scripts
├── .gitignore                         # Excludes secrets, databases, and caches
├── README.md                          # Master documentation
├── nit_system/                        # Django configuration package
│   ├── settings.py                    # 12-factor settings, security headers, WhiteNoise
│   ├── urls.py                        # Central URL dispatcher and error handlers
│   ├── wsgi.py                        # WSGI entrypoint for Gunicorn
│   └── asgi.py                        # ASGI entrypoint
├── apps/                              # Modular Django applications
│   ├── accounts/                      # Custom user model, RBAC backends, login/profile
│   ├── core/                          # Base layout, context processors, audit trail
│   ├── dashboard/                     # Central role dispatcher and executive dashboards
│   ├── master_data/                   # Products, customers, suppliers, materials, BOM
│   ├── inventory/                     # Ledger-based inventory, PO, GRN, adjustments
│   ├── production/                    # Work orders, batch execution, yield variance
│   ├── sales/                         # Sales orders, PDF tax invoice generator, dispatch
│   └── finance/                       # Receivables, payment vouchers, GST reports, exports
├── static/                            # Static CSS and JavaScript
│   ├── css/style.css                  # Custom styling, badges, and KPI stat-cards
│   └── js/main.js                     # Alert timers and credential auto-fill helpers
└── templates/                         # HTML templates extending base.html
```

---

## 7. Installation & Local Setup

### Prerequisites
* Python 3.11, 3.12, or 3.13
* Git

### Step 1: Clone the Repository
```bash
git clone https://github.com/akash2025it-gif/ManuFlow.git
cd ManuFlow
```

### Step 2: Create and Activate a Virtual Environment
```bash
# On Linux / macOS:
python3 -m venv venv
source venv/bin/activate

# On Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Apply Database Migrations
By default, the application runs on SQLite (`USE_SQLITE=True`) with zero external database setup required:
```bash
python manage.py migrate
```

### Step 5: Seed Demonstration Accounts & Benchmark Data
```bash
# 1. Create the 6 institutional staff role accounts
python manage.py seed_users

# 2. Populate opening inventory and standard BOM recipe
python manage.py seed_snacks_benchmark

# 3. Execute the production benchmark run (188 pkts output, variance alerts)
python manage.py run_nit_production_benchmark

# 4. Execute the sales benchmark (Retailer A invoice, Distributor B shortage)
python manage.py run_nit_sales_benchmark

# 5. Populate comprehensive enterprise demo data across all 8 modules
python manage.py seed_enterprise_demo_data
```

### Step 6: Start the Development Server
```bash
python manage.py runserver
```
Open your web browser and navigate to `http://127.0.0.1:8000/`.

---

## 8. Demonstration Credentials

### Official Cloud & Live Demonstration Account
ManuFlow includes a persistent, verified demonstration account configured for evaluation on both local and live deployments:

* **Email:** `demo@manuflow.app`
* **Password:** `ManuFlow@Demo2026!`
* **Role:** Business Owner / Executive Command Center (`/dashboard/owner/`)
* **Quick Login:** Use the **"Use Demo Account"** button on the login screen to autofill credentials instantly.

### Institutional Role-Specific Accounts (Local Evaluation)
For testing separation of duties across all 6 roles, use the following credentials with evaluation password `nit@12345`:

| Role | Login Identifier (Email / Username) | Password | Direct Dashboard Route |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin@nit.edu` / `admin` | `nit@12345` | `/dashboard/admin/` |
| **Salesman** | `salesman@nit.edu` / `salesman` | `nit@12345` | `/dashboard/sales/` |
| **Production** | `production@nit.edu` / `production` | `nit@12345` | `/dashboard/production/` |
| **Auditor** | `auditor@nit.edu` / `auditor` | `nit@12345` | `/dashboard/auditor/` |
| **Owner** | `owner@nit.edu` / `owner` | `nit@12345` | `/dashboard/owner/` |
| **Accountant** | `accountant@nit.edu` / `accountant` | `nit@12345` | `/finance/` |

*Security Guard*: In production (`DEBUG=False` and `DEMO_MODE=False`), one-click login helper buttons for institutional staff are hidden from the login screen and authentication using the shared `nit@12345` password is automatically rejected.

---

## 9. Environment Variables

Configure these settings in a `.env` file (copied from `.env.example`) or in your hosting environment:

| Variable | Default (Local) | Recommended (Production) | Description |
| :--- | :--- | :--- | :--- |
| `DEBUG` | `True` | `False` | Enables/disables debug mode and tracebacks |
| `SECRET_KEY` | *(Development key)* | *(50+ char random string)* | Cryptographic key for session and CSRF security |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | `.onrender.com,.vercel.app` | Whitelist of allowed HTTP Host headers |
| `CSRF_TRUSTED_ORIGINS`| `http://127.0.0.1:8000` | `https://manu-flow-ten.vercel.app` | Allowed origins for secure HTTPS form submissions |
| `DATABASE_URL` | *(None / SQLite)* | `postgresql://user:pass@host/db?sslmode=require` | Connection URL for PostgreSQL |
| `DEMO_MODE` | `True` | `False` | Controls demo login autofill and demo password validation |
| `SECURE_SSL_REDIRECT`| `False` | `True` | Enforces HTTPS redirection behind reverse proxies |

---

## 10. Automated Testing

ManuFlow includes a comprehensive automated test suite covering all 8 application modules (96 tests total, 100% passing):

```bash
python manage.py test apps.accounts apps.core apps.dashboard apps.master_data apps.inventory apps.production apps.sales apps.finance
```

### Coverage Overview (96 Automated Tests)
* **`accounts` (16 tests)**: User creation, dual email/username authentication, role permissions, session persistence, and password security guards.
* **`core` (6 tests)**: Context processors, custom 403/404/500 handlers, and immutable audit trail verification.
* **`dashboard` (6 tests)**: Role dispatcher, persona dashboard routing, KPI cards, and benchmark metrics calculation.
* **`master_data` (14 tests)**: Validation for products, pack sizes, customers, suppliers, UOM conversions, and BOM recipes.
* **`inventory` (18 tests)**: Purchase orders, GRN receipts, stock ledger invariants, adjustments, and low-stock alerts.
* **`production` (8 tests)**: Batch execution, consumption calculation, -6% yield variance alert triggers, and batch costing.
* **`sales` (6 tests)**: Order creation, stock availability checks, negative inventory guards, PDF tax invoice generation, and dispatch posting.
* **`finance` (22 tests)**: Receivables aging, partial/full payment vouchers, overpayment rejection, GST sales registers, and CSV/Excel XML export validation.

---

## 11. Cloud Deployment (Render + Neon)

ManuFlow is configured for deployment on **Render Free Web Service** paired with **Neon Free PostgreSQL**:

### Deployment Characteristics
* **100% Free Tier**: Uses Render's free compute allowance (750 hours/month) and Neon's serverless free PostgreSQL (0.5 GiB storage, no 30-day auto-expiry).
* **Automated Builds**: `build.sh` installs dependencies, collects static files via WhiteNoise, and applies database migrations directly to Neon.
* **Dynamic Port Binding**: Gunicorn binds to Render's dynamic port via `--bind 0.0.0.0:$PORT`.
* **Database Guard**: If `DEBUG=False` and `DATABASE_URL` is omitted, the build aborts immediately to prevent silent fallback to an ephemeral SQLite database.

### Deployment Steps
1. **Create Neon Database**: Sign up at [neon.tech](https://neon.tech), create a project (e.g. `manuflow`), and copy the Direct connection string:
   ```text
   postgresql://[user]:[password]@[endpoint].neon.tech/neondb?sslmode=require
   ```
2. **Deploy on Render**: In [dashboard.render.com](https://dashboard.render.com), click **New +** > **Blueprint**, and connect this repository.
3. **Configure `DATABASE_URL`**: When prompted by Render, paste your Neon connection string.
4. **Deploy**: Render executes `./build.sh` and launches the application.

### Creating the First Administrator (Post-Deployment)
*Note: Render Free does not include dashboard Shell access.* Because Neon PostgreSQL is accessible securely over TLS, run the admin creation command from your local terminal:

```powershell
# Windows PowerShell:
$env:DATABASE_URL="postgresql://[user]:[password]@[endpoint].neon.tech/neondb?sslmode=require"
python manage.py createsuperuser
Remove-Item Env:\DATABASE_URL

# Linux / macOS Bash:
export DATABASE_URL="postgresql://[user]:[password]@[endpoint].neon.tech/neondb?sslmode=require"
python manage.py createsuperuser
unset DATABASE_URL
```

---

## 12. Enterprise Demonstration & Compliance Notice

* **Demonstration Seller GSTIN**: `33NITTRICHY1Z5 (Demo Environment)` is utilized on invoices, dispatches, and reports as a registered demonstration environment tax identifier.
* **Document Status**: Invoices and delivery notes generated in demonstration environments conform to Section 31 statutory standards and are designated for operational evaluation.

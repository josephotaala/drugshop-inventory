# Trusteen Drug Center inventory system

A server-backed Django inventory application for Trusteen Drug Center. It includes authenticated access, product and stock management, sales/POS, stock receiving, supplier records, customer credit and repayments, expenses, alerts, reports, CSV export, JSON backup, and a server-side audit trail.

Each customer can have a separate account profile with a unique account number, order and receipt history, and tracked balance. Completing a sale opens its printable customer receipt; past receipts can also be reprinted from sales or the customer account.

## Run locally on Windows

Open PowerShell in this folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start the local MySQL service (for WampServer this is usually `wampmysqld64`; you may need to run PowerShell as Administrator), then sign in to MySQL as an administrator and create the database and app account. Use the supplied password for the account when replacing the SQL placeholder:

```sql
CREATE DATABASE IF NOT EXISTS trusteen_drugcenter
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'Trusteen Drugcenter'@'127.0.0.1';
ALTER USER 'Trusteen Drugcenter'@'127.0.0.1'
  IDENTIFIED BY 'replace-this-with-the-supplied-password';
GRANT ALL PRIVILEGES ON trusteen_drugcenter.* TO 'Trusteen Drugcenter'@'127.0.0.1';
```

Enter the app account password as a hidden prompt into the current PowerShell session, then initialize Django:

```powershell
$env:DB_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host -AsSecureString 'MySQL password')).Password
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
python manage.py runserver
```

The app defaults to MySQL on `127.0.0.1:3306`, database `trusteen_drugcenter`, and account `Trusteen Drugcenter`. Override these with `DB_NAME`, `DB_USER`, `DB_HOST`, and `DB_PORT` if needed. The password is read from `DB_PASSWORD`, not stored in source code. Re-enter it in each new PowerShell session. Open `http://127.0.0.1:8000/` and sign in with the superuser account you created. The demo command creates example inventory records and can be run again safely.

For development without MySQL, set `$env:DB_ENGINE = 'sqlite'` before running Django commands.

## Important

SQLite is configured for local development. Before live use, configure a production database, strong `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`, HTTPS, automated and tested backups, appropriate access roles, and applicable Ugandan pharmacy and privacy controls. The Django development server is not a production server. Mobile money collection, SMS/email, and offline synchronization are not integrated.

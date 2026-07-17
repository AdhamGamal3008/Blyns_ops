"""Finance module RBAC surface + posting vocabulary (docs/modules/FINANCE.md).

RBAC resource: `finance` — READ for GET/reports, WRITE for posting and
payments. §3: "Finance is the module most likely restricted to READ for many
roles — enforce strictly."
"""

from __future__ import annotations

RESOURCE = "finance"

# `accounts` is the chart of accounts — NOT CRM's customers, which live in
# `crm_accounts`. Both specs name `accounts`; see modules/crm/seed.py.

# Posting needs to find accounts by meaning, not by name (a tenant may rename
# them). The seeded starter chart's codes are that stable handle
# (modules/finance/seed.py STARTER_CHART).
ACCOUNT_CASH = "1000"
ACCOUNT_BANK = "1010"
ACCOUNT_AR = "1100"
ACCOUNT_AP = "2000"
ACCOUNT_TAX = "2100"
ACCOUNT_EQUITY = "3000"
ACCOUNT_INCOME = "4000"
ACCOUNT_COGS = "5000"

# Payment method → the account cash lands in / leaves from.
METHOD_ACCOUNTS = {"cash": ACCOUNT_CASH, "bank": ACCOUNT_BANK, "other": ACCOUNT_CASH}

ACCOUNT_TYPES = ["asset", "liability", "equity", "income", "expense"]

# Balance-sheet sign convention: assets and expenses grow on the debit side,
# everything else on the credit side.
DEBIT_NORMAL_TYPES = frozenset({"asset", "expense"})
CREDIT_NORMAL_TYPES = frozenset({"liability", "equity", "income"})

INVOICE_STATUSES = ["draft", "sent", "partly_paid", "paid", "void"]
OPEN_STATUSES = ["sent", "partly_paid"]  # what the dashboard KPI/calendar read

AGING_BUCKETS = [(0, 30), (31, 60), (61, 90)]  # plus a 90+ bucket

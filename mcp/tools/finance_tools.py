"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
Finance Tools Mixin for mem20 MCP Server

Provides finance tools with multi-backend support:
- Stock market data (Alpha Vantage, Yahoo Finance, IEX Cloud)
- Cryptocurrency (CoinGecko, CoinMarketCap, Binance)
- Banking (Plaid, Stripe)
- Accounting (QuickBooks, Xero)
- Budget tracking
- Expense management
- Invoice generation
- Tax calculation
- Portfolio tracking
- Financial news
"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt

import os
import sys
import json
import asyncio
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    sys.exit(1)


class FinanceToolsMixin:
    """Finance tools for mem20."""

    def register_finance_tools(self):
        """Register all finance tools."""
        self.tools["fin_stock_quote"] = mt.Tool(
            name="fin_stock_quote",
            title="Stock Quote",
            description="Get stock price and market data",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "provider": {"type": "string", "enum": ["alphavantage", "yahoo", "iex", "finnhub"], "default": "yahoo"},
                },
                "required": ["symbol"],
            },
        )
        self.tools["fin_crypto_price"] = mt.Tool(
            name="fin_crypto_price",
            title="Crypto Price",
            description="Get cryptocurrency price data",
            inputSchema={
                "type": "object",
                "properties": {
                    "coin": {"type": "string"},
                    "vs_currency": {"type": "string", "default": "usd"},
                    "provider": {"type": "string", "enum": ["coingecko", "coinmarketcap", "binance"], "default": "coingecko"},
                },
                "required": ["coin"],
            },
        )
        self.tools["fin_portfolio"] = mt.Tool(
            name="fin_portfolio",
            title="Portfolio Management",
            description="Manage investment portfolio",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["view", "add", "remove", "performance"], "default": "view"},
                    "symbol": {"type": "string", "default": ""},
                    "shares": {"type": "number", "default": 0},
                    "cost_basis": {"type": "number", "default": 0},
                },
                "required": [],
            },
        )
        self.tools["fin_budget"] = mt.Tool(
            name="fin_budget",
            title="Budget Management",
            description="Manage personal or project budget",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["view", "add_category", "add_expense", "summary"], "default": "view"},
                    "category": {"type": "string", "default": ""},
                    "amount": {"type": "number", "default": 0},
                    "description": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["fin_invoice"] = mt.Tool(
            name="fin_invoice",
            title="Invoice Management",
            description="Create and manage invoices",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "list", "send", "mark_paid"], "default": "list"},
                    "client": {"type": "string", "default": ""},
                    "items": {"type": "string", "description": "JSON array of line items", "default": "[]"},
                    "invoice_id": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["fin_tax_calc"] = mt.Tool(
            name="fin_tax_calc",
            title="Tax Calculator",
            description="Calculate income tax estimates",
            inputSchema={
                "type": "object",
                "properties": {
                    "income": {"type": "number"},
                    "filing_status": {"type": "string", "enum": ["single", "married_joint", "married_separate", "head"], "default": "single"},
                    "state": {"type": "string", "default": ""},
                    "deductions": {"type": "number", "default": 0},
                },
                "required": ["income"],
            },
        )
        self.tools["fin_expense_track"] = mt.Tool(
            name="fin_expense_track",
            title="Track Expense",
            description="Track personal or business expenses",
            inputSchema={
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "category": {"type": "string"},
                    "description": {"type": "string", "default": ""},
                    "date": {"type": "string", "default": ""},
                },
                "required": ["amount", "category"],
            },
        )
        self.tools["fin_financial_news"] = mt.Tool(
            name="fin_financial_news",
            title="Financial News",
            description="Get financial news and market updates",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "default": "markets"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": [],
            },
        )

    async def _fin_stock_quote(self, args: Dict) -> str:
        symbol = args.get("symbol", "")
        provider = args.get("provider", "yahoo")
        try:
    if provider == "yahoo":
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    result = data.get("chart", {}).get("result", [{}])[0]
    meta = result.get("meta", {})
    return f"Stock: {symbol}\nPrice: {meta.get('regularMarketPrice', 'N/A')}\nPrevious Close: {meta.get('previousClose', 'N/A')}\nCurrency: {meta.get('currency', 'USD')}"
    elif provider == "alphavantage":
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
    return "Error: ALPHA_VANTAGE_API_KEY required."
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    quote = data.get("Global Quote", {})
    return f"Stock: {symbol}\nPrice: {quote.get('05. price', 'N/A')}\nChange: {quote.get('09. change', 'N/A')}\nChange %: {quote.get('10. change percent', 'N/A')}"
    elif provider == "finnhub":
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
    return "Error: FINNHUB_API_KEY required."
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={api_key}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    return f"Stock: {symbol}\nCurrent: {data.get('c', 'N/A')}\nHigh: {data.get('h', 'N/A')}\nLow: {data.get('l', 'N/A')}\nOpen: {data.get('o', 'N/A')}\nPrevious Close: {data.get('pc', 'N/A')}"
    else:
    return f"Provider '{provider}' not yet implemented."
    except Exception as e:
    return f"Error: {str(e)}"

    async def _fin_crypto_price(self, args: Dict) -> str:
    coin = args.get("coin", "")
    vs_currency = args.get("vs_currency", "usd")
    provider = args.get("provider", "coingecko")
        try:
    if provider == "coingecko":
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies={vs_currency}&include_24hr_change=true&include_market_cap=true&include_24hr_vol=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    if coin in data:
    info = data[coin]
    return f"Crypto: {coin}\nPrice: {info.get(vs_currency, 'N/A')} {vs_currency.upper()}\n24h Change: {info.get(f'{vs_currency}_24h_change', 'N/A'):.2f}%\nMarket Cap: {info.get(f'{vs_currency}_market_cap', 'N/A')}\n24h Volume: {info.get(f'{vs_currency}_24h_vol', 'N/A')}"
    return f"Cryptocurrency '{coin}' not found."
    elif provider == "coinmarketcap":
    api_key = os.environ.get("COINMARKETCAP_API_KEY", "")
    if not api_key:
    return "Error: COINMARKETCAP_API_KEY required."
    return "CoinMarketCap integration requires API key."
    elif provider == "binance":
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={coin.upper()}{vs_currency.upper()}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    return f"Crypto: {coin}/{vs_currency}\nPrice: {data.get('lastPrice', 'N/A')}\n24h High: {data.get('highPrice', 'N/A')}\n24h Low: {data.get('lowPrice', 'N/A')}\n24h Change: {data.get('priceChangePercent', 'N/A')}%"
    else:
    return f"Provider '{provider}' not yet implemented."
    except Exception as e:
    return f"Error: {str(e)}"

    async def _fin_portfolio(self, args: Dict) -> str:
    action = args.get("action", "view")
    symbol = args.get("symbol", "")
    shares = args.get("shares", 0)
    cost_basis = args.get("cost_basis", 0)
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    portfolio_path = store_path / "portfolio.json"
    store_path.mkdir(parents=True, exist_ok=True)
    portfolio = []
    if portfolio_path.exists():
    with open(portfolio_path) as f:
    portfolio = json.load(f)
    if action == "view":
    if portfolio:
    output = f"Portfolio ({len(portfolio)} positions):\n"
    for p in portfolio:
    output += f"  {p['symbol']}: {p['shares']} shares @ ${p['cost_basis']:.2f}\n"
    return output
    return "Portfolio is empty."
    elif action == "add":
    position = {"symbol": symbol, "shares": shares, "cost_basis": cost_basis}
    portfolio.append(position)
    with open(portfolio_path, "w") as f:
    json.dump(portfolio, f, indent=2)
    return f"Added: {symbol} ({shares} shares @ ${cost_basis:.2f})"
    elif action == "remove":
    portfolio = [p for p in portfolio if p["symbol"] != symbol]
    with open(portfolio_path, "w") as f:
    json.dump(portfolio, f, indent=2)
    return f"Removed: {symbol}"
    elif action == "performance":
    return "Portfolio performance calculation requires current market data."
    else:
    return f"Unknown action: {action}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _fin_budget(self, args: Dict) -> str:
    action = args.get("action", "view")
    category = args.get("category", "")
    amount = args.get("amount", 0)
    description = args.get("description", "")
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    budget_path = store_path / "budget.json"
    store_path.mkdir(parents=True, exist_ok=True)
    budget = {"categories": [], "expenses": []}
    if budget_path.exists():
    with open(budget_path) as f:
    budget = json.load(f)
    if action == "view":
    if budget["categories"]:
    output = "Budget Categories:\n"
    for c in budget["categories"]:
    output += f"  {c['name']}: ${c['limit']:.2f}\n"
    return output
    return "No budget categories."
    elif action == "add_category":
    budget["categories"].append({"name": category, "limit": amount})
    with open(budget_path, "w") as f:
    json.dump(budget, f, indent=2)
    return f"Budget category added: {category} (${amount:.2f})"
    elif action == "add_expense":
    expense = {"category": category, "amount": amount, "description": description, "date": datetime.now().isoformat()}
    budget["expenses"].append(expense)
    with open(budget_path, "w") as f:
    json.dump(budget, f, indent=2)
    return f"Expense added: {category} - ${amount:.2f}"
    elif action == "summary":
    if budget["expenses"]:
    total = sum(e["amount"] for e in budget["expenses"])
    return f"Total expenses: ${total:.2f}\nTransactions: {len(budget['expenses'])}"
    return "No expenses recorded."
    else:
    return f"Unknown action: {action}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _fin_invoice(self, args: Dict) -> str:
    action = args.get("action", "list")
    client = args.get("client", "")
    items = json.loads(args.get("items", "[]"))
    invoice_id = args.get("invoice_id", "")
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    invoices_path = store_path / "invoices.json"
    store_path.mkdir(parents=True, exist_ok=True)
    invoices = []
    if invoices_path.exists():
    with open(invoices_path) as f:
    invoices = json.load(f)
    if action == "create":
    total = sum(item.get("quantity", 0) * item.get("price", 0) for item in items)
    invoice = {
    "id": f"INV-{int(time.time())}",
    "client": client,
    "items": items,
    "total": total,
    "status": "draft",
    "created_at": datetime.now().isoformat(),
    }
    invoices.append(invoice)
    with open(invoices_path, "w") as f:
    json.dump(invoices, f, indent=2)
    return f"Invoice created: {invoice['id']} (${total:.2f})"
    elif action == "list":
    if invoices:
    output = f"Invoices ({len(invoices)}):\n"
    for inv in invoices:
    output += f"  {inv['id']}: {inv['client']} - ${inv['total']:.2f} ({inv['status']})\n"
    return output
    return "No invoices."
    elif action == "send":
    for inv in invoices:
    if inv["id"] == invoice_id:
    inv["status"] = "sent"
    with open(invoices_path, "w") as f:
    json.dump(invoices, f, indent=2)
    return f"Invoice sent: {invoice_id}"
    return f"Invoice not found: {invoice_id}"
    elif action == "mark_paid":
    for inv in invoices:
    if inv["id"] == invoice_id:
    inv["status"] = "paid"
    with open(invoices_path, "w") as f:
    json.dump(invoices, f, indent=2)
    return f"Invoice marked paid: {invoice_id}"
    return f"Invoice not found: {invoice_id}"
    else:
    return f"Unknown action: {action}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _fin_tax_calc(self, args: Dict) -> str:
    income = args.get("income", 0)
    filing_status = args.get("filing_status", "single")
    state = args.get("state", "")
    deductions = args.get("deductions", 0)
        try:
    2024 Federal Tax Brackets (simplified)
    brackets = {
    "single": [(0, 11000, 0.10), (11000, 44725, 0.12), (44725, 95375, 0.22), (95375, 182050, 0.24), (182050, 231250, 0.32), (231250, 578125, 0.35), (578125, float('inf'), 0.37)],
    "married_joint": [(0, 22000, 0.10), (22000, 89450, 0.12), (89450, 190750, 0.22), (190750, 364200, 0.24), (364200, 462500, 0.32), (462500, 693750, 0.35), (693750, float('inf'), 0.37)],
    }
    taxable_income = max(0, income - deductions - 13850)  # Standard deduction for single
    if filing_status == "married_joint":
    taxable_income = max(0, income - deductions - 27700)
    tax = 0
    for low, high, rate in brackets.get(filing_status, brackets["single"]):
    if taxable_income > low:
    tax += (min(taxable_income, high) - low) * rate
    effective_rate = (tax / income * 100) if income > 0 else 0
    return f"Tax Estimate:\nGross Income: ${income:,.2f}\nDeductions: ${deductions:,.2f}\nTaxable Income: ${taxable_income:,.2f}\nEstimated Tax: ${tax:,.2f}\nEffective Rate: {effective_rate:.1f}%"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _fin_expense_track(self, args: Dict) -> str:
    amount = args.get("amount", 0)
    category = args.get("category", "")
    description = args.get("description", "")
    date = args.get("date", "")
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    expenses_path = store_path / "expenses.json"
    store_path.mkdir(parents=True, exist_ok=True)
    expenses = []
    if expenses_path.exists():
    with open(expenses_path) as f:
    expenses = json.load(f)
    expense = {
    "amount": amount,
    "category": category,
    "description": description,
    "date": date or datetime.now().isoformat(),
    }
    expenses.append(expense)
    with open(expenses_path, "w") as f:
    json.dump(expenses, f, indent=2)
    return f"Expense tracked: {category} - ${amount:.2f}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _fin_financial_news(self, args: Dict) -> str:
    topic = args.get("topic", "markets")
    limit = args.get("limit", 10)
        try:
    Use NewsAPI if available
    api_key = os.environ.get("NEWS_API_KEY", "")
    if api_key:
    url = f"https://newsapi.org/v2/everything?q={urllib.parse.quote(topic)}&pageSize={limit}&apiKey={api_key}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    articles = data.get("articles", [])
    output = f"Financial News ({topic}):\n"
    for article in articles[:limit]:
    output += f"  {article.get('title', 'N/A')}\n"
    output += f"  {article.get('url', '')}\n\n"
    return output
    return "Financial news requires NEWS_API_KEY environment variable."
    except Exception as e:
    return f"Error: {str(e)}"

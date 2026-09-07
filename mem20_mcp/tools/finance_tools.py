"""
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
import mcp_types as mt


import os
import sys
import json
import asyncio
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional



class FinanceToolsMixin:
    """Finance tools for mem20."""

    def register_finance_tools(self):
        """Register all finance tools."""
        self.tools["fin_stock_quote"] = mt.Tool(
            name="fin_stock_quote",
            title="Stock Quote",
            description="Get stock price and market data",
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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

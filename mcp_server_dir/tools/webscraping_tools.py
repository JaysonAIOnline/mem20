"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
Web Scraping Tools Mixin for mem20 MCP Server

Provides web scraping tools with multi-backend support:
- Static page scraping (requests + BeautifulSoup)
- Dynamic page scraping (Selenium, Playwright)
- API extraction
- RSS/Atom feed parsing
- Sitemap parsing
- Structured data extraction (JSON-LD, microdata)
- Image/media extraction
- Link extraction
- Form submission
- Rate limiting
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

# try:
    # from mcp.server import Server
    # from mcp.server.lowlevel.server import ServerRequestContext
    # import mcp_types as mt
# except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    # sys.exit(1)


class WebScrapingToolsMixin:
    """Web scraping tools for mem20."""

    def register_webscraping_tools(self):
        """Register all web scraping tools."""
        self.tools["scrape_page"] = mt.Tool(
            name="scrape_page",
            title="Scrape Web Page",
            description="Scrape a web page and extract content",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to scrape"},
                    "extract": {"type": "string", "enum": ["text", "html", "links", "images", "all"], "default": "text"},
                    "selector": {"type": "string", "description": "CSS selector to target", "default": ""},
                },
                "required": ["url"],
            },
        )
        self.tools["scrape_dynamic"] = mt.Tool(
            name="scrape_dynamic",
            title="Scrape Dynamic Page",
            description="Scrape a JavaScript-rendered page using Playwright",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to scrape"},
                    "wait_for": {"type": "string", "description": "CSS selector to wait for", "default": "body"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                    "extract": {"type": "string", "enum": ["text", "html", "screenshot"], "default": "text"},
                },
                "required": ["url"],
            },
        )
        self.tools["scrape_api"] = mt.Tool(
            name="scrape_api",
            title="Extract API Data",
            description="Extract data from a JSON/XML API",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "API URL"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "default": "GET"},
                    "headers": {"type": "string", "description": "JSON headers", "default": "{}"},
                    "body": {"type": "string", "description": "Request body", "default": ""},
                    "parse_path": {"type": "string", "description": "JSON path to extract", "default": ""},
                },
                "required": ["url"],
            },
        )
        self.tools["scrape_rss"] = mt.Tool(
            name="scrape_rss",
            title="Parse RSS/Atom Feed",
            description="Parse an RSS or Atom feed",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Feed URL"},
                    "limit": {"type": "integer", "description": "Max items", "default": 10},
                },
                "required": ["url"],
            },
        )
        self.tools["scrape_sitemap"] = mt.Tool(
            name="scrape_sitemap",
            title="Parse Sitemap",
            description="Parse an XML sitemap",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Sitemap URL"},
                    "limit": {"type": "integer", "description": "Max URLs", "default": 50},
                },
                "required": ["url"],
            },
        )
        self.tools["scrape_structured"] = mt.Tool(
            name="scrape_structured",
            title="Extract Structured Data",
            description="Extract JSON-LD, microdata, and schema.org data",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to extract from"},
                },
                "required": ["url"],
            },
        )
        self.tools["scrape_forms"] = mt.Tool(
            name="scrape_forms",
            title="Extract Forms",
            description="Extract form information from a page",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to analyze"},
                },
                "required": ["url"],
            },
        )
        self.tools["scrape_submit_form"] = mt.Tool(
            name="scrape_submit_form",
            title="Submit Form",
            description="Submit a form on a web page",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Form page URL"},
                    "form_data": {"type": "string", "description": "JSON object of form data"},
                    "form_index": {"type": "integer", "description": "Form index if multiple", "default": 0},
                },
                "required": ["url", "form_data"],
            },
        )

    async def _scrape_page(self, args: Dict) -> str:
        url = args.get("url", "")
        extract = args.get("extract", "text")
        selector = args.get("selector", "")
        # try:
            from bs4 import BeautifulSoup
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            if selector:
                elements = soup.select(selector)
                if extract == "text":
                    return "\n".join(el.get_text(strip=True) for el in elements)
                elif extract == "html":
                    return "\n".join(str(el) for el in elements)
                else:
                    return f"Found {len(elements)} elements."
            if extract == "text":
                return soup.get_text(separator="\n", strip=True)[:5000]
            elif extract == "html":
                return str(soup)[:5000]
            elif extract == "links":
                links = [a.get("href") for a in soup.find_all("a", href=True)]
                return "\n".join(links[:100])
            elif extract == "images":
                images = [img.get("src") for img in soup.find_all("img", src=True)]
                return "\n".join(images[:100])
            elif extract == "all":
                title = soup.title.string if soup.title else "No title"
                text = soup.get_text(separator="\n", strip=True)[:3000]
                links = [a.get("href") for a in soup.find_all("a", href=True)]
                return f"Title: {title}\n\nText:\n{text}\n\nLinks:\n" + "\n".join(links[:50])
            else:
                return f"Unknown extract type: {extract}"
        # except ImportError:
            return "Error: beautifulsoup4 not installed. Run: pip install beautifulsoup4"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _scrape_dynamic(self, args: Dict) -> str:
        url = args.get("url", "")
        wait_for = args.get("wait_for", "body")
        timeout = args.get("timeout", 30)
        extract = args.get("extract", "text")
        # try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(url, timeout=timeout * 1000)
                page.wait_for_selector(wait_for, timeout=timeout * 1000)
                if extract == "screenshot":
                    screenshot_path = f"/tmp/scrape_{int(time.time())}.png"
                    page.screenshot(path=screenshot_path)
                    browser.close()
                    return f"Screenshot saved to: {screenshot_path}"
                elif extract == "text":
                    text = page.inner_text("body")
                    browser.close()
                    return text[:5000]
                elif extract == "html":
                    html = page.content()
                    browser.close()
                    return html[:5000]
                else:
                    browser.close()
                    return f"Unknown extract type: {extract}"
        # except ImportError:
            return "Error: playwright not installed. Run: pip install playwright && playwright install"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _scrape_api(self, args: Dict) -> str:
        url = args.get("url", "")
        method = args.get("method", "GET")
        headers = json.loads(args.get("headers", "{}"))
        body = args.get("body", "")
        parse_path = args.get("parse_path", "")
        # try:
            if body:
                body = body.encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read().decode("utf-8")
            if parse_path:
                import jsonpath_ng
                json_data = json.loads(data)
                expr = jsonpath_ng.parse(parse_path)
                matches = [match.value for match in expr.find(json_data)]
                return json.dumps(matches, indent=2)
            return data[:5000]
        # except ImportError:
            return "Error: jsonpath-ng not installed for JSON path parsing."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _scrape_rss(self, args: Dict) -> str:
        url = args.get("url", "")
        limit = args.get("limit", 10)
        # try:
            import feedparser
            feed = feedparser.parse(url)
            if feed.bozo:
                return f"Error parsing feed: {feed.bozo_exception}"
            output = f"Feed: {feed.feed.title}\n"
            output += f"Entries: {len(feed.entries)}\n\n"
            for entry in feed.entries[:limit]:
                output += f"  {entry.title}\n"
                output += f"  {entry.link}\n"
                if hasattr(entry, "published"):
                    output += f"  {entry.published}\n"
                output += "\n"
            return output
        # except ImportError:
            return "Error: feedparser not installed. Run: pip install feedparser"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _scrape_sitemap(self, args: Dict) -> str:
        url = args.get("url", "")
        limit = args.get("limit", 50)
        # try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml = resp.read().decode("utf-8")
            import re
            urls = re.findall(r"<loc>(.*?)</loc>", xml)
            if not urls:
                return "No URLs found in sitemap."
            output = f"Sitemap URLs ({len(urls)}):\n"
            for u in urls[:limit]:
                output += f"  {u}\n"
            return output
        except Exception as e:
            return f"Error: {str(e)}"

    async def _scrape_structured(self, args: Dict) -> str:
        url = args.get("url", "")
        # try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            import re
            # Extract JSON-LD
            jsonld_pattern = r'<script type="application/ld\+json">(.*?)</script>'
            jsonld_matches = re.findall(jsonld_pattern, html, re.DOTALL)
            if jsonld_matches:
                output = "JSON-LD Data:\n"
                for match in jsonld_matches:
                    # try:
                        data = json.loads(match)
                        output += json.dumps(data, indent=2) + "\n"
                    except json.JSONDecodeError:
                        output += f"  (invalid JSON)\n"
                return output
            return "No structured data found."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _scrape_forms(self, args: Dict) -> str:
        url = args.get("url", "")
        # try:
            from bs4 import BeautifulSoup
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            forms = soup.find_all("form")
            if not forms:
                return "No forms found."
            output = f"Forms ({len(forms)}):\n"
            for i, form in enumerate(forms):
                output += f"\n  Form {i}:\n"
                output += f"    Action: {form.get('action', 'N/A')}\n"
                output += f"    Method: {form.get('method', 'GET')}\n"
                inputs = form.find_all("input")
                for inp in inputs:
                    output += f"    Input: {inp.get('name', 'N/A')} ({inp.get('type', 'text')})\n"
            return output
        # except ImportError:
            return "Error: beautifulsoup4 not installed."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _scrape_submit_form(self, args: Dict) -> str:
        url = args.get("url", "")
        form_data = json.loads(args.get("form_data", "{}"))
        form_index = args.get("form_index", 0)
        # try:
            from bs4 import BeautifulSoup
            import urllib.parse
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            forms = soup.find_all("form")
            if form_index >= len(forms):
                return f"Form index {form_index} out of range (found {len(forms)} forms)."
            form = forms[form_index]
            action = form.get("action", url)
            method = form.get("method", "GET").upper()
            if not action.startswith("http"):
                action = urllib.parse.urljoin(url, action)
            if method == "GET":
                data = urllib.parse.urlencode(form_data).encode("utf-8")
                full_url = f"{action}?{data.decode('utf-8')}"
                req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return f"Status: {resp.status}\n{resp.read().decode('utf-8', errors='ignore')[:2000]}"
            else:
                data = urllib.parse.urlencode(form_data).encode("utf-8")
                req = urllib.request.Request(action, data=data, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return f"Status: {resp.status}\n{resp.read().decode('utf-8', errors='ignore')[:2000]}"
        except Exception as e:
            return f"Error: {str(e)}"

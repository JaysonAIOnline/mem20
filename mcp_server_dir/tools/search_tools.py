"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
Search Tools Mixin for mem20 MCP Server

Provides search tools with multi-backend support:
- Web search (DuckDuckGo, Bing, Google)
- Local search (ripgrep, find)
- Knowledge base search
- Image search
- News search
- Academic search (arXiv, Semantic Scholar)
- Code search (GitHub)
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


class SearchToolsMixin:
    """Search tools for mem20."""

    def register_search_tools(self):
        """Register all search tools."""
        self.tools["search_web"] = mt.Tool(
            name="search_web",
            title="Web Search",
            description="Search the web using DuckDuckGo, Bing, or Google",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "engine": {"type": "string", "enum": ["duckduckgo", "bing", "google", "brave"], "default": "duckduckgo"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                    "safe_search": {"type": "boolean", "description": "Enable safe search", "default": True},
                },
                "required": ["query"],
            },
        )
        self.tools["search_local"] = mt.Tool(
            name="search_local",
            title="Local Search",
            description="Search files and directories locally",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern"},
                    "path": {"type": "string", "description": "Path to search", "default": "."},
                    "file_type": {"type": "string", "description": "File type filter", "default": ""},
                    "max_results": {"type": "integer", "description": "Max results", "default": 50},
                },
                "required": ["pattern"],
            },
        )
        self.tools["search_knowledge_base"] = mt.Tool(
            name="search_knowledge_base",
            title="Knowledge Base Search",
            description="Search mem20's knowledge base",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "category": {"type": "string", "description": "Filter by category", "default": ""},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
                "required": ["query"],
            },
        )
        self.tools["search_images"] = mt.Tool(
            name="search_images",
            title="Image Search",
            description="Search for images on the web",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "engine": {"type": "string", "enum": ["duckduckgo", "bing", "google"], "default": "duckduckgo"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                    "size": {"type": "string", "enum": ["small", "medium", "large"], "default": "medium"},
                },
                "required": ["query"],
            },
        )
        self.tools["search_news"] = mt.Tool(
            name="search_news",
            title="News Search",
            description="Search for news articles",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "engine": {"type": "string", "enum": ["duckduckgo", "bing", "google"], "default": "duckduckgo"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                    "time_range": {"type": "string", "enum": ["day", "week", "month", "year"], "default": "week"},
                },
                "required": ["query"],
            },
        )
        self.tools["search_academic"] = mt.Tool(
            name="search_academic",
            title="Academic Search",
            description="Search academic papers (arXiv, Semantic Scholar)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "source": {"type": "string", "enum": ["arxiv", "semantic_scholar", "both"], "default": "both"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                    "year_from": {"type": "integer", "description": "From year", "default": 0},
                    "year_to": {"type": "integer", "description": "To year", "default": 0},
                },
                "required": ["query"],
            },
        )
        self.tools["search_code"] = mt.Tool(
            name="search_code",
            title="Code Search",
            description="Search code on GitHub",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "language": {"type": "string", "description": "Programming language", "default": ""},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
                "required": ["query"],
            },
        )

    async def _search_web(self, args: Dict) -> str:
        query = args.get("query", "")
        engine = args.get("engine", "duckduckgo")
        limit = args.get("limit", 10)
        # try:
            if engine == "duckduckgo":
                # Use DuckDuckGo's lite HTML version
                url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                # Simple parsing of results
                results = []
                import re
                pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)">([^<]+)</a>.*?<a class="result__snippet" href="[^"]+">([^<]+)</a>'
                matches = re.findall(pattern, html, re.DOTALL)
                for url, title, snippet in matches[:limit]:
                    results.append(f"  {title.strip()}\n    URL: {url}\n    {snippet.strip()}\n")
                if results:
                    return f"Web Search Results ({len(results)}):\n" + "\n".join(results)
                else:
                    return "No results found."
            elif engine == "bing":
                url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={limit}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                import re
                results = []
                pattern = r'<h2><a href="([^"]+)"[^>]*>([^<]+)</a></h2>.*?<p[^>]*>([^<]+)</p>'
                matches = re.findall(pattern, html, re.DOTALL)
                for url, title, snippet in matches[:limit]:
                    results.append(f"  {title.strip()}\n    URL: {url}\n    {snippet.strip()}\n")
                if results:
                    return f"Web Search Results ({len(results)}):\n" + "\n".join(results)
                else:
                    return "No results found."
            else:
                return f"Engine '{engine}' not yet implemented."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _search_local(self, args: Dict) -> str:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        file_type = args.get("file_type", "")
        max_results = args.get("max_results", 50)
        # try:
            import subprocess
            import shutil
            rg_path = shutil.which("rg")
            if rg_path:
                cmd = [rg_path, "--no-heading", "--line-number", "--max-count", str(max_results)]
                if file_type:
                    cmd.extend(["-g", f"*.{file_type}"])
                cmd.extend([pattern, path])
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    return f"Local Search Results:\n{result.stdout}"
                else:
                    return "No results found."
            else:
                # Fallback to grep
                cmd = ["grep", "-r", "-n", "--include", f"*.{file_type}" if file_type else "*", pattern, path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    return f"Local Search Results:\n{result.stdout}"
                else:
                    return "No results found."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _search_knowledge_base(self, args: Dict) -> str:
        query = args.get("query", "")
        category = args.get("category", "")
        limit = args.get("limit", 10)
        # try:
            store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
            kb_path = store_path / "knowledge_base"
            if not kb_path.exists():
                return "Knowledge base is empty."
            results = []
            for file in kb_path.rglob("*.md"):
                content = file.read_text()
                if query.lower() in content.lower():
                    if category and category.lower() not in content.lower():
                        continue
                    results.append(f"  {file.name}: {content[:200]}...")
                if len(results) >= limit:
                    break
            if results:
                return f"Knowledge Base Results ({len(results)}):\n" + "\n".join(results)
            else:
                return "No results found."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _search_images(self, args: Dict) -> str:
        query = args.get("query", "")
        engine = args.get("engine", "duckduckgo")
        limit = args.get("limit", 10)
        # try:
            if engine == "duckduckgo":
                url = f"https://duckduckgo.com/?q={urllib.parse.quote(query)}&iax=images&ia=images"
                return f"Image search URL: {url}\n(DuckDuckGo image search requires JavaScript. Use the URL to view results.)"
            else:
                return f"Image search for '{query}' on {engine} not yet implemented."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _search_news(self, args: Dict) -> str:
        query = args.get("query", "")
        engine = args.get("engine", "duckduckgo")
        limit = args.get("limit", 10)
        time_range = args.get("time_range", "week")
        # try:
            if engine == "duckduckgo":
                url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}&df={time_range}&ia=news"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                import re
                results = []
                pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)">([^<]+)</a>'
                matches = re.findall(pattern, html, re.DOTALL)
                for url, title in matches[:limit]:
                    results.append(f"  {title.strip()}\n    URL: {url}\n")
                if results:
                    return f"News Search Results ({len(results)}):\n" + "\n".join(results)
                else:
                    return "No news found."
            else:
                return f"News search on {engine} not yet implemented."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _search_academic(self, args: Dict) -> str:
        query = args.get("query", "")
        source = args.get("source", "both")
        limit = args.get("limit", 10)
        year_from = args.get("year_from", 0)
        year_to = args.get("year_to", 0)
        results = []
        # try:
            if source in ["arxiv", "both"]:
                arxiv_url = f"http://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(query)}&max_results={limit}"
                req = urllib.request.Request(arxiv_url)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    xml = resp.read().decode("utf-8")
                import re
                entries = re.findall(r'<entry>(.*?)</entry>', xml, re.DOTALL)
                for entry in entries[:limit]:
                    title = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
                    summary = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
                    published = re.search(r'<published>(.*?)</published>', entry)
                    if title:
                        t = title.group(1).strip().replace("\n", " ")
                        s = summary.group(1).strip().replace("\n", " ")[:200] if summary else ""
                        p = published.group(1)[:4] if published else ""
                        results.append(f"  [arXiv {p}] {t}\n    {s}\n")
            if source in ["semantic_scholar", "both"]:
                ss_url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(query)}&limit={limit}&fields=title,year,abstract"
                req = urllib.request.Request(ss_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for paper in data.get("data", [])[:limit]:
                    title = paper.get("title", "")
                    year = paper.get("year", "")
                    abstract = paper.get("abstract", "")[:200] if paper.get("abstract") else ""
                    results.append(f"  [SS {year}] {title}\n    {abstract}\n")
            if results:
                return f"Academic Search Results ({len(results)}):\n" + "\n".join(results)
            else:
                return "No academic papers found."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _search_code(self, args: Dict) -> str:
        query = args.get("query", "")
        language = args.get("language", "")
        limit = args.get("limit", 10)
        # try:
            import subprocess
            # Use GitHub search via gh CLI if available
            gh_path = shutil.which("gh")
            if gh_path:
                cmd = [gh_path, "search", "code", query, "--limit", str(limit)]
                if language:
                    cmd.extend(["--language", language])
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    return f"Code Search Results:\n{result.stdout}"
                else:
                    return f"Error: {result.stderr}"
            else:
                return "GitHub CLI (gh) not found. Install gh to search code."
        except Exception as e:
            return f"Error: {str(e)}"

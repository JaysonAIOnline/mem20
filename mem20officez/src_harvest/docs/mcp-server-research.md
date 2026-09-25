# MCP Server Research — Best Servers by Bot Category

> **Research Date:** September 2, 2026
> **Purpose:** Identify high-quality MCP servers for each bot category in the mem20 claw plugin fleet
> **Method:** Web searches across official registries (registry.modelcontextprotocol.io, GitHub MCP Registry, Glama, Smithery, MCP.so, PulseMCP), community rankings, and category-specific queries
> **Note:** This is research only — no servers have been installed.

---

## 1. Business / Analyst (Financial Data, Market Research, CRM)

| # | Server | Description | Install / URL | Stars |
|---|--------|-------------|---------------|-------|
| 1 | **Equibles MCP** | 108 tools for US equity market data: SEC filings, earnings calls, institutional/insider holdings, congressional trades, short data, fund holdings, macro indicators. ALVIS AI analyst built in. | `https://mcp.equibles.com/mcp` (remote) | — |
| 2 | **Alpha Vantage MCP** | Real-time/historical stock prices, options, indices, technical indicators, forex, crypto, fundamentals. Official MCP endpoint. | `https://www.alphavantage.co/support/#api-key` + MCP config | — |
| 3 | **Financial Modeling Prep (FMP) MCP** | Strongest for fundamentals — income statements, ratios, earnings, technical indicators. US and international markets. | Community MCP wrapper around FMP API | — |
| 4 | **EODHD MCP** | 72 read-only tools: prices, fundamentals, news, technicals, US options, ESG, macro. Free API key. | `eodhd.com/lp/eodhd-mcp-server` | — |
| 5 | **LLMQuant Data MCP** | Wiki articles, research papers, crypto/equity prices, prediction markets, macro indicators, SEC filings, ETF holdings. | `@llmquant/data-mcp` (npm) | — |

**Also considered:** Octagon AI (investment research), Finnhub (real-time), Polygon.io (multi-asset), Yahoo Finance MCP (no-auth, simple).

---

## 2. Advertising (Ad Platforms, Analytics, Copywriting)

| # | Server | Description | Install / URL | Stars |
|---|--------|-------------|---------------|-------|
| 1 | **Synter MCP** | 140+ tools across 19 ad platforms. Full campaign creation on 14 (Google, Meta, LinkedIn, TikTok, Reddit, Pinterest, Snapchat, X, Microsoft, Amazon, The Trade Desk, etc.). AI creative generation. | `npx @synterai/mcp-server` or `https://mcp.syntermedia.ai/mcp/` | — |
| 2 | **Adspirer** | 430 tools across 6 platforms (Google, Meta, Amazon, TikTok, LinkedIn, ChatGPT Ads). Full R/W with guardrails. | `https://mcp.adspirer.com/mcp` (remote) | — |
| 3 | **Google Ads MCP (Official)** | Read-only. Query reports, metrics, metadata via GAQL. Open-source Python. | `googleads/google-ads-mcp` (GitHub) | — |
| 4 | **Meta Ads AI Connectors (Official)** | Open beta. 29 tools: reporting, campaign management, catalogs, signal diagnostics. Full R/W. | `https://mcp.facebook.com/ads` (hosted) | — |
| 5 | **BlueAlpha MCP** | Google + Meta + TikTok + LinkedIn with 51 pre-built decision-layer skills (audits, creative fatigue, MMM integration). | Remote SaaS | — |

**Also considered:** Pipeboard (Meta, mature OSS), Ryze AI (Google+Meta+GA4, 250+ tools), Markifact (cross-platform), Metadata (141 tools, autonomous ad ops).

---

## 3. Beta Testing (Bug Tracking, Test Management, Feedback)

| # | Server | Description | Install / URL | Stars |
|---|--------|-------------|---------------|-------|
| 1 | **Microsoft Playwright MCP** | Browser automation via structured accessibility tree. Screenshots, form filling, web scraping, E2E testing. | `npx @playwright/mcp` | 28K+ |
| 2 | **Argus** | AI-powered exploratory QA agent. Finds bugs like a real user. 34/34 capability score. Screen mode for macOS apps. | `pip install argus-testing` | — |
| 3 | **yo-bug** | MCP server for human-in-the-loop testing. Users point/click/type bugs; AI gets element locations, console errors, annotated screenshots. | npm package | — |
| 4 | **SmartBear MCP** | BearQ, BugSnag, Reflect, Swagger, PactFlow, QMetry, Zephyr, Collaborator. Full testing suite. | `https://bugsnag.mcp.smartbear.com/mcp` (remote) | 44 |
| 5 | **MK QA Master** | Universal test runner: pytest, Jest, Cypress, Go, Maestro (mobile), Schemathesis (API), Newman (Postman). | `pip install mk-qa-master` | — |

**Also considered:** TestSprite (AI-first autonomous testing), Selenium MCP, Appium MCP, UI Debugger MCP, Fuzzing MCP Server.

---

## 4. Skill Research (MCP Registries, Tool Discovery)

| # | Server | Description | Install / URL | Stars |
|---|--------|-------------|---------------|-------|
| 1 | **MCPfinder** | Searches 25,000+ MCP servers across Official Registry, Glama, and Smithery. Exposes `search_mcp_servers`, `get_server_details`, `get_install_config`. | `npx @mcpfinder/server` | — |
| 2 | **Official MCP Registry** | Community-driven registry by Anthropic/GitHub/PulseMCP/Microsoft. REST API for server metadata. | `registry.modelcontextprotocol.io` | 7.2K |
| 3 | **GitHub MCP Registry** | Curated directory of MCP servers. One-click install in VS Code. Sorted by stars and activity. | `github.com/mcp-registry` | — |
| 4 | **Glama** | 81,811 MCP servers, 15,929 connectors, 653,987 tools. Inspector & gateway. Quality-scored. | `glama.ai` | — |
| 5 | **MCP Market** | 10,000+ servers across 23+ categories. Browsable web UI with filtering. | `mcpmarket.com` | — |

**Also considered:** MCP.so (19,000+ servers), PulseMCP, Smithery (7,000+ servers with hosted runtime), TrueFoundry (enterprise gateway).

---

## 5. Game Development (Unity, Unreal, Game Assets)

| # | Server | Description | Install / URL | Stars |
|---|--------|-------------|---------------|-------|
| 1 | **Unity MCP (Official)** | First-party Unity MCP server. Live editor context: hierarchy, GameObjects, components, console. Editor actions + script editing. | Unity Package Manager (Unity 6+) | — |
| 2 | **Unreal MCP (Epic Official)** | First-party Unreal MCP plugin (UE 5.7/5.8). Deep editor control: Blueprints, actors, sequencer, Niagara, AI, animation. | Epic Plugin (built-in) | — |
| 3 | **AnkleBreaker Unity MCP** | 200+ tools across 30+ categories. Scene management, physics, terrain, Shader Graph, NavMesh, profiling, MPPM multiplayer. | GitHub (MIT) | — |
| 4 | **GameDev All-in-One MCP** | 67 tools across Roblox, Unity, Unreal, and Blender. Single server, multi-engine. | `npx @dmae97/gamedev-all-in-one-mcp` | — |
| 5 | **ChiR24 Unreal MCP** | 23+ canonical tools: asset management, Blueprint editing, actor control, Sequencer, Niagara, AI, networking. Native C++ plugin. | GitHub (MIT) | 850 |

**Also considered:** Godot MCP (137 tools, 18 categories), StraySpark Blender MCP (404 tools), mcp-unreal (Go binary, 49 tools), GameDev-MCP-Server (engine-agnostic).

---

## 6. Web Development (Frontend, Backend, Deployment)

| # | Server | Description | Install / URL | Stars |
|---|--------|-------------|---------------|-------|
| 1 | **GitHub MCP (Official)** | Repos, PRs, issues, Actions, code search, file reads. Remote OAuth endpoint. | `https://api.githubcopilot.com/mcp/` | 32K+ |
| 2 | **Vercel MCP** | Deployments, environment variables, build logs, project management. | Remote endpoint (OAuth) | — |
| 3 | **Supabase MCP** | Database, auth, storage, edge functions, SQL workflows. | Remote endpoint | — |
| 4 | **Context7** | Up-to-date, version-specific library documentation injected into prompts. | `npx @upstash/context7-mcp` | 48K+ |
| 5 | **DeployHQ MCP** | Deployment triggers, rollbacks, server management. | Remote endpoint | — |

**Also considered:** Figma MCP (design-to-code), Playwright MCP (browser testing), Railway MCP, DigitalOcean MCP, Vibe Deploy (VPS deployment), WebDeploy MCP, Kebab MCP (97+ tools, Vercel-hosted).

---

## 7. Cloud / DevOps (AWS, GCP, Azure, CI/CD)

| # | Server | Description | Install / URL | Stars |
|---|--------|-------------|---------------|-------|
| 1 | **Azure DevOps MCP (Microsoft Official)** | #1 DevOps MCP (97.17 score). Pipelines, work items, repos, boards. 45 contributors. | `npx @microsoft/azure-devops-mcp` | 1.4K |
| 2 | **AWS MCP Server (AWS Labs)** | Remote managed server. Full AWS API support, IAM-based permissions, CloudTrail audit logging. | `uvx mcp-proxy-for-aws@latest` | 3.7K |
| 3 | **gcloud MCP (Google Official)** | Broad gcloud CLI coverage. Compute, GKE, BigQuery, IAM. | `npx @googleapis/gcloud-mcp` | 705 |
| 4 | **Kubernetes MCP (Official)** | K8s and OpenShift cluster management. Pods, deployments, logs, Helm. | `npx @containers/kubernetes-mcp-server` | 1.3K |
| 5 | **Harness MCP** | 11 tools, 220 resource types. CI/CD, GitOps, Feature Flags, Cloud Cost, Security Testing, Chaos Engineering. | npm package | — |

**Also considered:** Terraform MCP (HashiCorp), Docker MCP, Lens MCP Server, Aegis MCP (DevSecOps), AutoForge (multi-cloud), Infra-Ops MCP (92 tools), AWS DevOps MCP Server (49 tools).

---

## 8. Research (Academic, Web Search, Data Analysis)

| # | Server | Description | Install / URL | Stars |
|---|--------|-------------|---------------|-------|
| 1 | **Retrievr MCP** | 61 source plugins: ArXiv, PubMed, Semantic Scholar, OpenAlex, HuggingFace, Europe PMC, CrossRef, GitHub, Wikipedia, etc. | Go library + MCP server | — |
| 2 | **Open Search MCP** | 33 specialized search tools: arXiv, PubMed, IEEE, Semantic Scholar, Brave, SearXNG, deep research. | GitHub (MIT) | — |
| 3 | **Web Research MCP** | 7 tools: Brave/Tavily search, Jina Reader, Wikipedia, arXiv, HN, StackExchange, Crossref. Deep research pipeline. | `npx @infinit3labs/web-research-mcp` | — |
| 4 | **RivalSearch MCP** | 5 web engines, 9 social platforms, 5 academic DBs, news aggregation, conflict detection. No API keys. | `npx @damionrashford/rivalsearch-mcp` | — |
| 5 | **Academic Research MCP** | arXiv, Semantic Scholar, CrossRef, PubMed. Citation networks, trend analysis, RAG with ChromaDB, Zotero sync. | GitHub | — |

**Also considered:** Paper Search MCP Node.js (14 academic platforms), resp_mcp (conference-aware), WET MCP (SearXNG + academic), My Research MCP Server (47 tools, DuckDB analytics).

---

## 9. GitHub (Code Review, Project Management)

| # | Server | Description | Install / URL | Stars |
|---|--------|-------------|---------------|-------|
| 1 | **GitHub MCP Server (Official)** | 60+ tools: repos, PRs, issues, Actions, code search, security scanning. Remote OAuth. | `https://api.githubcopilot.com/mcp/` | 32K+ |
| 2 | **github-codemunch-mcp** | Indexes repos into symbols. Returns signatures/summaries instead of whole files. Token-efficient. | `npx @jgravelle/jcodemunch-mcp` | 2.6K |
| 3 | **Code Review MCP** | GitHub + GitLab PR/MR review. Static analysis (Ruff, Bandit). 13-category engineering checklist. | `uvx code-review-mcp` | — |
| 4 | **Octocode MCP** | Code archaeology: local ripgrep/LSP + GitHub PR search + npm/PyPI lookup. 13 tools. | `npx @bgauryy/octocode` | 920 |
| 5 | **MCP GitHub Project Manager** | 84 tools for GitHub Projects V2: sprints, milestones, issues, PRs, metrics. | GitHub | 95 |

**Also considered:** TAI MCP GitHub PR (focused PR review), Jira-GitHub MCP (end-to-end workflow), GitHub Security MCP (39 audit tools), idea-reality-mcp (competitor scanning).

---

## 10. 3D / Blender (Rendering, Modeling, Animation)

| # | Server | Description | Install / URL | Stars |
|---|--------|-------------|---------------|-------|
| 1 | **Blender MCP (Official)** | Lightweight MCP server for Blender. Natural language interface with bpy. Scene analysis, geometry nodes docs. | Blender Extension (.mcpb) | — |
| 2 | **RFingAdam MCP Blender** | 218 tools: modeling, materials, sculpting, animation, rendering, MSFS content, AI 3D generation (Hyper3D, Meshy, Tripo). | GitHub | — |
| 3 | **StraySpark Blender MCP v3** | 404 tools across 39 categories. Vision feedback (JPEG <200KB), checkpoints/transactions, runtime discovery, CC0 assets. | GitHub | — |
| 4 | **Blender MCP Pro** | 120+ tools: scene, materials, shader nodes, lights, modifiers, animation, geometry nodes, camera, rendering, UV, rigging. | GitHub | — |
| 5 | **Blender AI MCP** | Production-shaped: goal-first routing, curated tools, deterministic verification, vision-assisted modeling. | GitHub (FastMCP) | — |

**Also considered:** namurokuro Blender MCP (50+ tools), macson Blender MCP (17 tools, Antigravity), Blender Studio Pro MCP (220+ tools, search+execute), PatrykIti Blender AI MCP.

---

## Summary Statistics

| Category | Servers Researched | Top Pick |
|----------|-------------------|----------|
| Business/Analyst | 10+ | Equibles MCP (108 tools, SEC/FRED/CFTC data) |
| Advertising | 10+ | Synter MCP (19 platforms, 140+ tools) |
| Beta Testing | 10+ | Microsoft Playwright MCP (28K+ stars) |
| Skill Research | 8+ | MCPfinder (25,000+ servers indexed) |
| Game Development | 10+ | Unity MCP (Official) / AnkleBreaker (200+ tools) |
| Web Development | 10+ | GitHub MCP (Official, 32K+ stars) |
| Cloud/DevOps | 15+ | Azure DevOps MCP (97.17 score, #1 DevOps) |
| Research | 10+ | Retrievr MCP (61 source plugins) |
| GitHub | 10+ | GitHub MCP Server (Official) |
| 3D/Blender | 10+ | RFingAdam MCP Blender (218 tools) |

---

## Key Registries & Discovery Resources

- **Official MCP Registry:** `registry.modelcontextprotocol.io` — 26,624+ servers tracked
- **GitHub MCP Registry:** Curated directory with one-click VS Code install
- **Glama:** `glama.ai` — 81,811 servers, quality-scored
- **Smithery:** Hosted + local MCP servers, 7,000+
- **MCP.so:** 19,000+ community-submitted servers
- **PulseMCP:** 11,946+ stars, composite scoring
- **MCP Market:** 10,000+ servers, 23+ categories, browsable UI
- **MCP.Directory:** 3,000+ servers with one-click install
- **MCPfinder:** MCP server that searches MCP servers (meta!)

---

## Recommendations

1. **Start with official/first-party servers** where available (GitHub, Unity, Unreal, Google Ads, Meta Ads, AWS, Azure, Kubernetes) — they have the best maintenance and security.

2. **For cross-platform needs**, prefer unified servers (Synter for ads, Retrievr for research, GameDev All-in-One for game engines) to reduce configuration overhead.

3. **Use MCPfinder or Glama** for ongoing discovery as the ecosystem evolves rapidly.

4. **Security considerations:** Prefer OAuth-based remote servers over local API key storage. Use read-only defaults and scope permissions narrowly.

5. **The ecosystem is maturing fast** — official vendor servers are increasingly available, reducing reliance on community wrappers.
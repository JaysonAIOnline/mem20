# Open WebUI Computer + Jayson — Installation & Connection

This is the official computer/agent companion made by the Open WebUI team.  
It gives the agent a real computer (files, terminal, browser, git, etc.).

## 1. Install Open WebUI Computer

Open WebUI Computer is a **separate project** from the main Open WebUI.

1. Go to the official Open WebUI Computer repository / docs
2. Follow the installation instructions (usually Docker-based)
3. Start a workspace

It will expose an OpenAI-compatible gateway for that workspace.

## 2. Connect to Jayson

1. In Jayson go to **Admin Panel → Connections**
2. Add a new OpenAI-compatible connection
3. Use the URL and key provided by your Open WebUI Computer workspace
   - Typical form: `http://host.docker.internal:PORT/v1`

4. Save

Each workspace appears as a selectable model that has full computer access.

## 3. Why this is powerful

- Native fit with Jayson
- Real file system + terminal + browser
- Designed to work as the “action layer” while Jayson is the control / chat layer
- Excellent for coding and system tasks together with your 3D tools

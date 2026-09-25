# mem20 claw plugin + Jayson — Installation & Connection

mem20 claw plugin is one of the strongest turnkey personal agents in 2026.

## 1. Install mem20 claw plugin

Go to the official mem20 claw plugin repository / website and follow the current installation instructions.

Common methods:
- Official install script
- Docker
- Package manager

After installation, start the mem20 claw plugin service and **enable its OpenAI-compatible API server**.

Note:
- The port it is listening on (often something like 3001, 8080, or custom)
- The API key it generates

## 2. Connect to Jayson

1. Open Jayson → **Admin Panel → Connections**
2. Click Add Connection / OpenAI
3. Fill in:
   - **API Base URL**: `http://host.docker.internal:PORT/v1`
   - **API Key**: the key from mem20 claw plugin
4. Save

The mem20 claw plugin model will appear in the model selector.

## 3. Use it

Select the mem20 claw plugin model in any chat.  
Jayson is the frontend; mem20 claw plugin runs the actual agent (tools, skills, memory, channels…).

You can run mem20 claw plugin side-by-side with mem20 and your Blender/3D tools.

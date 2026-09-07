"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
Communication Tools Mixin for mem20 MCP Server

Provides communication tools with multi-backend support:
- Email (SMTP, IMAP, Gmail, Outlook)
- SMS (Twilio)
- Slack integration
- Discord integration
- Telegram integration
- WhatsApp (via Twilio)
- Push notifications
- Calendar invites
- Meeting scheduling
- Contact management
"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt

import os
import sys
import json
import asyncio
import smtplib
import imaplib
from pathlib import Path
from typing import Any, Dict, List, Optional

# try:
    # from mcp.server import Server
    # from mcp.server.lowlevel.server import ServerRequestContext
    # import mcp_types as mt
# except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    # sys.exit(1)


class CommunicationToolsMixin:
    """Communication tools for mem20."""

    def register_communication_tools(self):
        """Register all communication tools."""
        self.tools["comm_send_email"] = mt.Tool(
            name="comm_send_email",
            title="Send Email",
            description="Send an email via SMTP",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "html": {"type": "boolean", "default": False},
                    "cc": {"type": "string", "default": ""},
                    "bcc": {"type": "string", "default": ""},
                },
                "required": ["to", "subject", "body"],
            },
        )
        self.tools["comm_read_email"] = mt.Tool(
            name="comm_read_email",
            title="Read Emails",
            description="Read emails from IMAP inbox",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder": {"type": "string", "default": "INBOX"},
                    "limit": {"type": "integer", "default": 10},
                    "unread_only": {"type": "boolean", "default": True},
                    "search": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["comm_slack_message"] = mt.Tool(
            name="comm_slack_message",
            title="Send Slack Message",
            description="Send a message to a Slack channel or user",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "message": {"type": "string"},
                    "thread_ts": {"type": "string", "default": ""},
                    "blocks": {"type": "string", "default": ""},
                },
                "required": ["channel", "message"],
            },
        )
        self.tools["comm_discord_message"] = mt.Tool(
            name="comm_discord_message",
            title="Send Discord Message",
            description="Send a message to a Discord channel via webhook",
            inputSchema={
                "type": "object",
                "properties": {
                    "webhook_url": {"type": "string"},
                    "message": {"type": "string"},
                    "username": {"type": "string", "default": ""},
                    "avatar_url": {"type": "string", "default": ""},
                },
                "required": ["webhook_url", "message"],
            },
        )
        self.tools["comm_telegram_message"] = mt.Tool(
            name="comm_telegram_message",
            title="Send Telegram Message",
            description="Send a message via Telegram bot",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": {"type": "string"},
                    "message": {"type": "string"},
                    "parse_mode": {"type": "string", "enum": ["Markdown", "HTML"], "default": "Markdown"},
                    "bot_token": {"type": "string", "default": ""},
                },
                "required": ["chat_id", "message"],
            },
        )
        self.tools["comm_sms_send"] = mt.Tool(
            name="comm_sms_send",
            title="Send SMS",
            description="Send an SMS via Twilio",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "message": {"type": "string"},
                    "from_number": {"type": "string", "default": ""},
                },
                "required": ["to", "message"],
            },
        )
        self.tools["comm_push_notify"] = mt.Tool(
            name="comm_push_notify",
            title="Push Notification",
            description="Send a push notification via Pushover or similar",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "message": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "normal", "high", "emergency"], "default": "normal"},
                    "service": {"type": "string", "enum": ["pushover", "ntfy", "pushbullet"], "default": "ntfy"},
                },
                "required": ["title", "message"],
            },
        )
        self.tools["comm_calendar_invite"] = mt.Tool(
            name="comm_calendar_invite",
            title="Calendar Invite",
            description="Create a calendar invite (.ics file)",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "attendees": {"type": "string", "description": "Comma-separated emails", "default": ""},
                    "description": {"type": "string", "default": ""},
                    "location": {"type": "string", "default": ""},
                },
                "required": ["title", "start_time", "end_time"],
            },
        )
        self.tools["comm_contact_manage"] = mt.Tool(
            name="comm_contact_manage",
            title="Manage Contacts",
            description="Add, update, or search contacts",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "update", "search", "list"], "default": "list"},
                    "name": {"type": "string", "default": ""},
                    "email": {"type": "string", "default": ""},
                    "phone": {"type": "string", "default": ""},
                    "notes": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )

    async def _comm_send_email(self, args: Dict) -> str:
        to = args.get("to", "")
        subject = args.get("subject", "")
        body = args.get("body", "")
        html = args.get("html", False)
        cc = args.get("cc", "")
        bcc = args.get("bcc", "")
        # try:
            smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
            smtp_port = int(os.environ.get("SMTP_PORT", "587"))
            smtp_user = os.environ.get("SMTP_USER", "")
            smtp_pass = os.environ.get("SMTP_PASS", "")
            if not smtp_user or not smtp_pass:
                return "Error: SMTP_USER and SMTP_PASS environment variables required."
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            msg = MIMEMultipart()
            msg["From"] = smtp_user
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc
            if html:
                msg.attach(MIMEText(body, "html"))
            else:
                msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            return f"Email sent to {to}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _comm_read_email(self, args: Dict) -> str:
        folder = args.get("folder", "INBOX")
        limit = args.get("limit", 10)
        unread_only = args.get("unread_only", True)
        search = args.get("search", "")
        # try:
            imap_host = os.environ.get("IMAP_HOST", "imap.gmail.com")
            imap_user = os.environ.get("IMAP_USER", "")
            imap_pass = os.environ.get("IMAP_PASS", "")
            if not imap_user or not imap_pass:
                return "Error: IMAP_USER and IMAP_PASS environment variables required."
            mail = imaplib.IMAP4_SSL(imap_host)
            mail.login(imap_user, imap_pass)
            mail.select(folder)
            if search:
                _, data = mail.search(None, f'(SUBJECT "{search}")')
            elif unread_only:
                _, data = mail.search(None, "UNSEEN")
            else:
                _, data = mail.search(None, "ALL")
            email_ids = data[0].split()[-limit:]
            output = f"Emails ({len(email_ids)}):\n"
            for eid in reversed(email_ids):
                _, msg_data = mail.fetch(eid, "(RFC822)")
                output += f"  Email ID: {eid}\n"
            mail.logout()
            return output
        except Exception as e:
            return f"Error: {str(e)}"

    async def _comm_slack_message(self, args: Dict) -> str:
        channel = args.get("channel", "")
        message = args.get("message", "")
        thread_ts = args.get("thread_ts", "")
        blocks = args.get("blocks", "")
        # try:
            import urllib.request
            slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
            if not slack_token:
                return "Error: SLACK_BOT_TOKEN environment variable required."
            payload = {"channel": channel, "text": message}
            if thread_ts:
                payload["thread_ts"] = thread_ts
            if blocks:
                payload["blocks"] = json.loads(blocks)
            req = urllib.request.Request(
                "https://slack.com/api/chat.postMessage",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {slack_token}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return f"Message sent to {channel}"
            return f"Error: {data.get('error', 'Unknown error')}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _comm_discord_message(self, args: Dict) -> str:
        webhook_url = args.get("webhook_url", "")
        message = args.get("message", "")
        username = args.get("username", "")
        avatar_url = args.get("avatar_url", "")
        # try:
            import urllib.request
            payload = {"content": message}
            if username:
                payload["username"] = username
            if avatar_url:
                payload["avatar_url"] = avatar_url
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return f"Message sent (status: {resp.status})"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _comm_telegram_message(self, args: Dict) -> str:
        chat_id = args.get("chat_id", "")
        message = args.get("message", "")
        parse_mode = args.get("parse_mode", "Markdown")
        bot_token = args.get("bot_token", "")
        # try:
            import urllib.request
            if not bot_token:
                bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            if not bot_token:
                return "Error: TELEGRAM_BOT_TOKEN environment variable required."
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": parse_mode}
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return f"Message sent to {chat_id}"
            return f"Error: {data.get('description', 'Unknown error')}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _comm_sms_send(self, args: Dict) -> str:
        to = args.get("to", "")
        message = args.get("message", "")
        from_number = args.get("from_number", "")
        # try:
            from twilio.rest import Client
            account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
            auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
            if not from_number:
                from_number = os.environ.get("TWILIO_FROM_NUMBER", "")
            if not account_sid or not auth_token:
                return "Error: TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN required."
            client = Client(account_sid, auth_token)
            msg = client.messages.create(body=message, from_=from_number, to=to)
            return f"SMS sent (SID: {msg.sid})"
        # except ImportError:
            return "Error: twilio not installed. Run: pip install twilio"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _comm_push_notify(self, args: Dict) -> str:
        title = args.get("title", "")
        message = args.get("message", "")
        priority = args.get("priority", "normal")
        service = args.get("service", "ntfy")
        # try:
            import urllib.request
            if service == "ntfy":
                topic = os.environ.get("NTFY_TOPIC", "mem20")
                url = f"https://ntfy.sh/{topic}"
                req = urllib.request.Request(
                    url,
                    data=message.encode("utf-8"),
                    headers={"Title": title, "Priority": priority},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return f"Notification sent (status: {resp.status})"
            elif service == "pushover":
                token = os.environ.get("PUSHOVER_TOKEN", "")
                user = os.environ.get("PUSHOVER_USER", "")
                if not token or not user:
                    return "Error: PUSHOVER_TOKEN and PUSHOVER_USER required."
                payload = {"token": token, "user": user, "title": title, "message": message, "priority": 0}
                req = urllib.request.Request(
                    "https://api.pushover.net/1/messages.json",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return f"Notification sent (status: {resp.status})"
            else:
                return f"Service '{service}' not yet implemented."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _comm_calendar_invite(self, args: Dict) -> str:
        title = args.get("title", "")
        start_time = args.get("start_time", "")
        end_time = args.get("end_time", "")
        attendees = args.get("attendees", "")
        description = args.get("description", "")
        location = args.get("location", "")
        # try:
            ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//mem20//EN
BEGIN:VEVENT
DTSTART:{start_time}
DTEND:{end_time}
SUMMARY:{title}
DESCRIPTION:{description}
LOCATION:{location}
"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
            if attendees:
                for email in attendees.split(","):
                    ics_content += f"ATTENDEE:mailto:{email.strip()}\n"
            ics_content += """END:VEVENT
END:VCALENDAR"""
            output_path = f"/tmp/calendar_invite_{int(time.time())}.ics"
            with open(output_path, "w") as f:
                f.write(ics_content)
            return f"Calendar invite created: {output_path}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _comm_contact_manage(self, args: Dict) -> str:
        action = args.get("action", "list")
        name = args.get("name", "")
        email = args.get("email", "")
        phone = args.get("phone", "")
        notes = args.get("notes", "")
        # try:
            store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
            contacts_path = store_path / "contacts.json"
            store_path.mkdir(parents=True, exist_ok=True)
            contacts = []
            if contacts_path.exists():
                with open(contacts_path) as f:
                    contacts = json.load(f)
            if action == "add":
                contact = {"name": name, "email": email, "phone": phone, "notes": notes}
                contacts.append(contact)
                with open(contacts_path, "w") as f:
                    json.dump(contacts, f, indent=2)
                return f"Contact added: {name}"
            elif action == "search":
                results = [c for c in contacts if name.lower() in c.get("name", "").lower()]
                if results:
                    return f"Contacts ({len(results)}):\n" + "\n".join(f"  {c['name']}: {c['email']}" for c in results)
                return "No contacts found."
            elif action == "list":
                if contacts:
                    return f"Contacts ({len(contacts)}):\n" + "\n".join(f"  {c['name']}: {c['email']}" for c in contacts)
                return "No contacts."
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            return f"Error: {str(e)}"

"""
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
import mcp_types as mt


import os
import sys
import json
import asyncio
import smtplib
import imaplib
from pathlib import Path
from typing import Any, Dict, List, Optional



class CommunicationToolsMixin:
    """Communication tools for mem20."""

    def register_communication_tools(self):
        """Register all communication tools."""
        self.tools["comm_send_email"] = mt.Tool(
            name="comm_send_email",
            title="Send Email",
            description="Send an email via SMTP",
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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

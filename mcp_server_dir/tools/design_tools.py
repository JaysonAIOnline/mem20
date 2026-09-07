"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
Design Tools Mixin for mem20 MCP Server

Provides design tools with multi-backend support:
- Image generation (DALL-E, Midjourney, Stable Diffusion)
- Image editing (resize, crop, filter, convert)
- Color palette generation
- Typography tools
- Layout/grid calculations
- SVG generation
- Figma integration
- Canva integration
- UI component generation
- Design system management
- Asset optimization
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


class DesignToolsMixin:
    """Design tools for mem20."""

    def register_design_tools(self):
        """Register all design tools."""
        self.tools["design_image_generate"] = mt.Tool(
            name="design_image_generate",
            title="Generate Image",
            description="Generate images using AI (DALL-E, Stable Diffusion)",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "provider": {"type": "string", "enum": ["dalle", "stable_diffusion", "midjourney"], "default": "dalle"},
                    "size": {"type": "string", "enum": ["256x256", "512x512", "1024x1024"], "default": "1024x1024"},
                    "style": {"type": "string", "enum": ["natural", "vivid", "artistic", "photographic"], "default": "natural"},
                },
                "required": ["prompt"],
            },
        )
        self.tools["design_image_edit"] = mt.Tool(
            name="design_image_edit",
            title="Edit Image",
            description="Edit images (resize, crop, rotate, filter)",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string"},
                    "action": {"type": "string", "enum": ["resize", "crop", "rotate", "flip", "blur", "sharpen", "grayscale", "convert"], "default": "resize"},
                    "width": {"type": "integer", "default": 0},
                    "height": {"type": "integer", "default": 0},
                    "format": {"type": "string", "enum": ["png", "jpg", "webp", "gif"], "default": "png"},
                    "quality": {"type": "integer", "default": 85},
                },
                "required": ["image_path", "action"],
            },
        )
        self.tools["design_color_palette"] = mt.Tool(
            name="design_color_palette",
            title="Color Palette",
            description="Generate color palettes",
            inputSchema={
                "type": "object",
                "properties": {
                    "base_color": {"type": "string", "default": "#3498db"},
                    "scheme": {"type": "string", "enum": ["monochromatic", "complementary", "analogous", "triadic", "tetradic", "random"], "default": "analogous"},
                    "count": {"type": "integer", "default": 5},
                },
                "required": [],
            },
        )
        self.tools["design_typography"] = mt.Tool(
            name="design_typography",
            title="Typography",
            description="Typography tools and font pairing",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["pair", "scale", "preview"], "default": "pair"},
                    "font": {"type": "string", "default": ""},
                    "text": {"type": "string", "default": "Sample Text"},
                    "size": {"type": "integer", "default": 16},
                },
                "required": [],
            },
        )
        self.tools["design_svg_generate"] = mt.Tool(
            name="design_svg_generate",
            title="Generate SVG",
            description="Generate SVG graphics programmatically",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["circle", "rect", "line", "polygon", "path", "text", "gradient", "pattern"], "default": "circle"},
                    "width": {"type": "integer", "default": 200},
                    "height": {"type": "integer", "default": 200},
                    "fill": {"type": "string", "default": "#3498db"},
                    "stroke": {"type": "string", "default": "#2c3e50"},
                    "stroke_width": {"type": "integer", "default": 2},
                    "content": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["design_figma"] = mt.Tool(
            name="design_figma",
            title="Figma Integration",
            description="Interact with Figma files and components",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["get_file", "get_components", "export", "comment"], "default": "get_file"},
                    "file_key": {"type": "string", "default": ""},
                    "node_id": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["design_ui_component"] = mt.Tool(
            name="design_ui_component",
            title="Generate UI Component",
            description="Generate HTML/CSS UI components",
            inputSchema={
                "type": "object",
                "properties": {
                    "component": {"type": "string", "enum": ["button", "card", "navbar", "form", "modal", "table", "alert", "badge", "pagination"], "default": "button"},
                    "style": {"type": "string", "enum": ["minimal", "modern", "glass", "neumorphism", "skeuomorphic"], "default": "modern"},
                    "theme": {"type": "string", "enum": ["light", "dark"], "default": "light"},
                    "framework": {"type": "string", "enum": ["html", "react", "vue", "tailwind"], "default": "html"},
                },
                "required": [],
            },
        )
        self.tools["design_asset_optimize"] = mt.Tool(
            name="design_asset_optimize",
            title="Optimize Assets",
            description="Optimize images and assets for web",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "type": {"type": "string", "enum": ["image", "svg", "font"], "default": "image"},
                    "quality": {"type": "integer", "default": 80},
                    "max_width": {"type": "integer", "default": 1920},
                },
                "required": ["path"],
            },
        )

    async def _design_image_generate(self, args: Dict) -> str:
        prompt = args.get("prompt", "")
        provider = args.get("provider", "dalle")
        size = args.get("size", "1024x1024")
        style = args.get("style", "natural")
        # try:
            if provider == "dalle":
                api_key = os.environ.get("OPENAI_API_KEY", "")
                if not api_key:
                    return "Error: OPENAI_API_KEY required for DALL-E."
                return f"DALL-E image generation: '{prompt}' ({size}, {style}). Requires OpenAI API call."
            elif provider == "stable_diffusion":
                api_key = os.environ.get("STABILITY_API_KEY", "")
                if not api_key:
                    return "Error: STABILITY_API_KEY required for Stable Diffusion."
                return f"Stable Diffusion image generation: '{prompt}' ({size}, {style}). Requires Stability API call."
            elif provider == "midjourney":
                return "Midjourney integration requires Discord bot setup."
            else:
                return f"Unknown provider: {provider}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _design_image_edit(self, args: Dict) -> str:
        image_path = args.get("image_path", "")
        action = args.get("action", "resize")
        width = args.get("width", 0)
        height = args.get("height", 0)
        fmt = args.get("format", "png")
        quality = args.get("quality", 85)
        # try:
            from PIL import Image, ImageFilter
            img = Image.open(image_path)
            if action == "resize" and width and height:
                img = img.resize((width, height))
            elif action == "crop" and width and height:
                img = img.crop((0, 0, width, height))
            elif action == "rotate":
                img = img.rotate(90, expand=True)
            elif action == "flip":
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            elif action == "blur":
                img = img.filter(ImageFilter.BLUR)
            elif action == "sharpen":
                img = img.filter(ImageFilter.SHARPEN)
            elif action == "grayscale":
                img = img.convert("L")
            output_path = f"{image_path}_edited.{fmt}"
            img.save(output_path, quality=quality)
            return f"Image edited: {output_path}"
        # except ImportError:
            return "Error: Pillow not installed. Run: pip install Pillow"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _design_color_palette(self, args: Dict) -> str:
        base_color = args.get("base_color", "#3498db")
        scheme = args.get("scheme", "analogous")
        count = args.get("count", 5)
        # try:
            import colorsys
            # Convert hex to RGB
            r = int(base_color[1:3], 16) / 255
            g = int(base_color[3:5], 16) / 255
            b = int(base_color[5:7], 16) / 255
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            colors = []
            if scheme == "monochromatic":
                for i in range(count):
                    new_v = max(0.2, min(1.0, v * (0.5 + i * 0.25)))
                    new_r, new_g, new_b = colorsys.hsv_to_rgb(h, s, new_v)
                    colors.append(f"#{int(new_r*255):02x}{int(new_g*255):02x}{int(new_b*255):02x}")
            elif scheme == "complementary":
                colors.append(base_color)
                comp_h = (h + 0.5) % 1.0
                new_r, new_g, new_b = colorsys.hsv_to_rgb(comp_h, s, v)
                colors.append(f"#{int(new_r*255):02x}{int(new_g*255):02x}{int(new_b*255):02x}")
                for i in range(count - 2):
                    new_h = (h + (i + 1) * 0.1) % 1.0
                    new_r, new_g, new_b = colorsys.hsv_to_rgb(new_h, s, v)
                    colors.append(f"#{int(new_r*255):02x}{int(new_g*255):02x}{int(new_b*255):02x}")
            elif scheme == "analogous":
                for i in range(count):
                    new_h = (h + (i - count // 2) * 0.05) % 1.0
                    new_r, new_g, new_b = colorsys.hsv_to_rgb(new_h, s, v)
                    colors.append(f"#{int(new_r*255):02x}{int(new_g*255):02x}{int(new_b*255):02x}")
            elif scheme == "triadic":
                for i in range(min(count, 3)):
                    new_h = (h + i * 0.333) % 1.0
                    new_r, new_g, new_b = colorsys.hsv_to_rgb(new_h, s, v)
                    colors.append(f"#{int(new_r*255):02x}{int(new_g*255):02x}{int(new_b*255):02x}")
            else:
                import random
                for _ in range(count):
                    new_r, new_g, new_b = colorsys.hsv_to_rgb(random.random(), s, v)
                    colors.append(f"#{int(new_r*255):02x}{int(new_g*255):02x}{int(new_b*255):02x}")
            return f"Color Palette ({scheme}):\n" + "\n".join(f"  {c}" for c in colors)
        except Exception as e:
            return f"Error: {str(e)}"

    async def _design_typography(self, args: Dict) -> str:
        action = args.get("action", "pair")
        font = args.get("font", "")
        text = args.get("text", "Sample Text")
        size = args.get("size", 16)
        # try:
            if action == "pair":
                pairings = {
                    "Helvetica": "Georgia",
                    "Arial": "Times New Roman",
                    "Roboto": "Merriweather",
                    "Open Sans": "Lora",
                    "Montserrat": "Playfair Display",
                }
                pairs = []
                for heading, body in pairings.items():
                    pairs.append(f"  {heading} + {body}")
                return "Font Pairings:\n" + "\n".join(pairs)
            elif action == "scale":
                # Generate a type scale
                ratio = 1.25
                sizes = []
                for i in range(-2, 5):
                    s = round(size * (ratio ** i))
                    sizes.append(f"  Level {i+2}: {s}px")
                return "Type Scale:\n" + "\n".join(sizes)
            elif action == "preview":
                return f"Typography Preview:\nFont: {font or 'Default'}\nSize: {size}px\nText: {text}"
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _design_svg_generate(self, args: Dict) -> str:
        svg_type = args.get("type", "circle")
        width = args.get("width", 200)
        height = args.get("height", 200)
        fill = args.get("fill", "#3498db")
        stroke = args.get("stroke", "#2c3e50")
        stroke_width = args.get("stroke_width", 2)
        content = args.get("content", "")
        # try:
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            if svg_type == "circle":
                svg += f'<circle cx="{width//2}" cy="{height//2}" r="{min(width,height)//3}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
            elif svg_type == "rect":
                svg += f'<rect x="10" y="10" width="{width-20}" height="{height-20}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
            elif svg_type == "line":
                svg += f'<line x1="0" y1="0" x2="{width}" y2="{height}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
            elif svg_type == "polygon":
                points = f"{width//2},0 {width},{height} 0,{height}"
                svg += f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
            elif svg_type == "text":
                svg += f'<text x="{width//2}" y="{height//2}" text-anchor="middle" fill="{fill}" font-size="20">{content}</text>'
            elif svg_type == "gradient":
                svg += f'<defs><linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color{fill};stop-opacity:1"/><stop offset="100%" style="stop-color{stroke};stop-opacity:1"/></linearGradient></defs><rect width="{width}" height="{height}" fill="url(#grad)"/>'
            svg += '</svg>'
            output_path = f"/tmp/design_{svg_type}_{int(time.time())}.svg"
            with open(output_path, "w") as f:
                f.write(svg)
            return f"SVG generated: {output_path}\n{svg}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _design_figma(self, args: Dict) -> str:
        action = args.get("action", "get_file")
        file_key = args.get("file_key", "")
        node_id = args.get("node_id", "")
        # try:
            api_key = os.environ.get("FIGMA_ACCESS_TOKEN", "")
            if not api_key:
                return "Error: FIGMA_ACCESS_TOKEN required."
            if action == "get_file":
                url = f"https://api.figma.com/v1/files/{file_key}"
                req = urllib.request.Request(url, headers={"X-Figma-Token": api_key})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return f"Figma File: {data.get('name', 'N/A')}\nLast Modified: {data.get('lastModified', 'N/A')}"
            elif action == "get_components":
                url = f"https://api.figma.com/v1/files/{file_key}/components"
                req = urllib.request.Request(url, headers={"X-Figma-Token": api_key})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                components = data.get("meta", {}).get("components", [])
                return f"Components ({len(components)}):\n" + "\n".join(f"  {c.get('name', 'N/A')}" for c in components[:20])
            else:
                return f"Action '{action}' not yet implemented."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _design_ui_component(self, args: Dict) -> str:
        component = args.get("component", "button")
        style = args.get("style", "modern")
        theme = args.get("theme", "light")
        framework = args.get("framework", "html")
        # try:
            colors = {
                "light": {"bg": "#ffffff", "text": "#333333", "primary": "#3498db", "border": "#dddddd"},
                "dark": {"bg": "#1a1a1a", "text": "#ffffff", "primary": "#3498db", "border": "#333333"},
            }
            c = colors[theme]
            if component == "button":
                if framework == "html":
                    return f'<button style="background:{c["primary"]};color:{c["text"]};border:none;padding:12px 24px;border-radius:6px;cursor:pointer;">Button</button>'
                elif framework == "tailwind":
                    return f'<button class="bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600">Button</button>'
            elif component == "card":
                if framework == "html":
                    return f'<div style="background:{c["bg"]};border:1px solid {c["border"]};border-radius:8px;padding:16px;"><h3 style="color:{c["text"]};">Card Title</h3><p style="color:{c["text"]};">Card content</p></div>'
            return f"Component '{component}' with framework '{framework}' not yet implemented."
        except Exception as e:
            return f"Error: {str(e)}"

    async def _design_asset_optimize(self, args: Dict) -> str:
        path = args.get("path", "")
        asset_type = args.get("type", "image")
        quality = args.get("quality", 80)
        max_width = args.get("max_width", 1920)
        # try:
            if asset_type == "image":
                from PIL import Image
                img = Image.open(path)
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height))
                output_path = f"{path}_optimized.webp"
                img.save(output_path, "WEBP", quality=quality)
                return f"Image optimized: {output_path}"
            elif asset_type == "svg":
                # SVGO optimization would go here
                return f"SVG optimization for {path} requires svgo."
            else:
                return f"Asset type '{asset_type}' not yet implemented."
        # except ImportError:
            return "Error: Pillow not installed."
        except Exception as e:
            return f"Error: {str(e)}"

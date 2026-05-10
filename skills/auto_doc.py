#!/usr/bin/env python3
"""
auto_doc.py — FRIDAY Auto Documentation Engine
================================================
Scans project structure and uses Gemini to generate real documentation.
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


API_CONFIG_PATH = get_base_dir() / "config" / "api_keys.json"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _generate(prompt: str, system: str = "") -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_get_api_key())
    config = types.GenerateContentConfig(
        system_instruction=system if system else None,
        max_output_tokens=2048,
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )
    return response.text.strip()


class AutoDocEngine:
    """Generates real project documentation using structure analysis + Gemini."""

    def __init__(self, output_dir: str = "documentation"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def scan_project(self, project_path: str = ".") -> dict:
        """Scan project structure and collect metadata."""
        root = Path(project_path).resolve()
        structure = {}
        file_count = 0
        total_lines = 0
        languages = {}

        for item in sorted(root.rglob("*")):
            if item.is_file() and not any(
                p.startswith(".") for p in item.relative_to(root).parts
            ):
                rel = str(item.relative_to(root))
                # Skip common non-source dirs
                if any(d in rel for d in ["__pycache__", "node_modules", ".git", "venv", ".env"]):
                    continue

                file_count += 1
                ext = item.suffix.lower()
                languages[ext] = languages.get(ext, 0) + 1

                # Count lines for text files
                if ext in (".py", ".js", ".ts", ".md", ".txt", ".json", ".yaml", ".yml"):
                    try:
                        lines = len(item.read_text(encoding="utf-8", errors="ignore").splitlines())
                        total_lines += lines
                        structure[rel] = {"lines": lines, "ext": ext}
                    except Exception:
                        structure[rel] = {"ext": ext}
                else:
                    structure[rel] = {"ext": ext}

        return {
            "root": str(root),
            "name": root.name,
            "file_count": file_count,
            "total_lines": total_lines,
            "languages": languages,
            "structure": structure,
        }

    def generate_docs(self, project_name: Optional[str] = None,
                      project_path: str = ".") -> str:
        """Generate comprehensive project documentation."""
        scan = self.scan_project(project_path)
        name = project_name or scan["name"]

        # Build structure summary for the LLM
        structure_lines = []
        for path, meta in list(scan["structure"].items())[:100]:
            lines_info = f" ({meta['lines']}L)" if "lines" in meta else ""
            structure_lines.append(f"  {path}{lines_info}")
        structure_text = "\n".join(structure_lines)

        lang_summary = ", ".join(
            f"{ext}: {count}" for ext, count in
            sorted(scan["languages"].items(), key=lambda x: -x[1])[:10]
        )

        # Read key files for context
        key_files = []
        for pattern in ["README.md", "SOUL.md", "CLAUDE.md", "main.py", "setup.py"]:
            p = Path(project_path) / pattern
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")[:2000]
                    key_files.append(f"--- {pattern} ---\n{content}")
                except Exception:
                    pass

        key_files_text = "\n\n".join(key_files[:5])

        prompt = (
            f"Generate comprehensive documentation for the project '{name}'.\n\n"
            f"Project stats: {scan['file_count']} files, {scan['total_lines']} lines\n"
            f"Languages: {lang_summary}\n\n"
            f"File structure:\n{structure_text}\n\n"
            f"Key files:\n{key_files_text[:3000]}\n\n"
            f"Generate:\n"
            f"1. Project Overview (what it does, purpose)\n"
            f"2. Architecture (how it's organized, key components)\n"
            f"3. Setup & Installation\n"
            f"4. Key Modules & Their Roles\n"
            f"5. Configuration\n"
            f"6. Usage Examples\n\n"
            f"Write in clear, professional markdown. Be specific — reference actual files and modules."
        )

        system = (
            "You are a technical writer. Generate clear, accurate documentation "
            "based on the provided project structure and files. "
            "Use proper markdown formatting. Be specific and reference actual files."
        )

        try:
            doc_content = _generate(prompt, system=system)
        except Exception as e:
            doc_content = f"Documentation generation failed: {e}\n\nFallback: Manual review needed."

        # Add header
        header = (
            f"# {name} — Documentation\n\n"
            f"*Auto-generated by FRIDAY Auto-Doc Engine on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
            f"**Stats:** {scan['file_count']} files | {scan['total_lines']} lines | "
            f"Languages: {lang_summary}\n\n---\n\n"
        )

        full_doc = header + doc_content

        # Save
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Docs_{name}_{timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_doc)

        return filepath

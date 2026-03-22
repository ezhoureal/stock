#!/usr/bin/env python3
"""
Parse akshare_stock.md into hierarchical, index-based structure for RAG/MCP.

This script converts the large AKShare API documentation into:
1. JSON index with hierarchical structure
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


@dataclasses.dataclass
class Parameter:
    """API parameter definition."""

    name: str
    type_: str
    description: str
    required: bool = False


@dataclasses.dataclass
class APIEntry:
    """Single API endpoint documentation."""

    name: str  # 接口 name
    title: str  # Section title (#####)
    url: str  # 目标地址
    description: str  # 描述
    limit: str  # 限量
    input_params: list[Parameter]  # 输入参数
    output_params: list[Parameter]  # 输出参数
    example_code: str  # 接口示例
    example_data: str  # 数据示例
    context: dict[str, Any]  # Hierarchical context


@dataclasses.dataclass
class Section:
    """Documentation section at any level."""

    level: int  # 1-5, corresponds to # to #####
    name: str
    parent: Section | None = None
    children: list[Section] = dataclasses.field(default_factory=list)
    apis: list[APIEntry] = dataclasses.field(default_factory=list)

    @property
    def path(self) -> str:
        """Get full path string."""
        parts = []
        curr = self
        while curr:
            parts.append(curr.name)
            curr = curr.parent
        return " > ".join(reversed(parts))


def parse_markdown_table(content: list[str]) -> list[dict[str, str]]:
    """Parse a markdown table into list of dicts."""
    if not content or len(content) < 2:
        return []

    # Parse header
    header_match = re.match(r"^\|?(.+)\|?$", content[0])
    if not header_match:
        return []

    headers = [h.strip() for h in header_match.group(1).split("|")]
    headers = [h for h in headers if h]

    # Parse separator (skip)
    if len(content) < 3:
        return []

    # Parse rows
    rows = []
    for line in content[2:]:
        row_match = re.match(r"^\|?(.+)\|?$", line.strip())
        if row_match:
            values = [v.strip() for v in row_match.group(1).split("|")]
            values = [v for v in values if v or len(values) == len(headers)]
            if values:
                row_dict = {}
                for i, h in enumerate(headers):
                    row_dict[h] = values[i] if i < len(values) else ""
                rows.append(row_dict)

    return rows


def extract_params_table(lines: list[str], start_idx: int) -> tuple[list[Parameter], int]:
    """Extract and parse input/output parameters table."""
    params = []
    i = start_idx
    table_content = []

    # Find and parse the table
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|"):
            table_content.append(line)
        elif table_content:  # Table ended
            break
        i += 1

    if table_content:
        rows = parse_markdown_table(table_content)
        for row in rows:
            param_name = row.get("名称", "")
            param_type = row.get("类型", "")
            desc = row.get("描述", "")
            if param_name and param_name != "-":
                params.append(Parameter(param_name, param_type, desc))

    return params, i


def extract_code_block(lines: list[str], start_idx: int) -> tuple[str, int]:
    """Extract code block starting at given index."""
    if not lines[start_idx].strip().startswith("```"):
        return "", start_idx

    code_lines = []
    i = start_idx + 1

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            return "\n".join(code_lines), i + 1
        code_lines.append(line)
        i += 1

    return "\n".join(code_lines), i


def extract_data_example(lines: list[str], start_idx: int) -> tuple[str, int]:
    """Extract data example block (typically in backticks)."""
    content = []
    i = start_idx

    while i < len(lines):
        line = lines[i]
        if line.strip() == "```" and content:
            return "\n".join(content), i + 1
        if line.strip():
            content.append(line)
        i += 1

    return "\n".join(content), i


def parse_api_entry_at(
    lines: list[str], start_idx: int, context: dict[str, Any]
) -> APIEntry | None:
    """Parse a single API entry starting at the '接口:' line."""
    i = start_idx

    # Get API name from "接口:" line
    name = lines[i].replace("接口:", "").strip()
    if not name:
        return None
    i += 1

    # Get title from context (the nearest heading)
    title = context.get("level_5", "") or context.get("level_4", "")

    # Parse fields
    url = ""
    description = ""
    limit = ""
    input_params: list[Parameter] = []
    output_params: list[Parameter] = []
    example_code = ""
    example_data = ""

    while i < len(lines):
        line = lines[i].strip()

        # Stop at next section or next API entry
        if line.startswith("#") or line.startswith("接口:"):
            break

        if line.startswith("目标地址:"):
            url = line.replace("目标地址:", "").strip()
        elif line.startswith("描述:"):
            description = line.replace("描述:", "").strip()
        elif line.startswith("限量:"):
            limit = line.replace("限量:", "").strip()
        elif line.startswith("输入参数"):
            input_params, i = extract_params_table(lines, i + 1)
            continue
        elif line.startswith("输出参数"):
            output_params, i = extract_params_table(lines, i + 1)
            continue
        elif line.startswith("接口示例"):
            # Skip the "接口示例" line
            i += 1
            if i < len(lines):
                example_code, i = extract_code_block(lines, i)
            continue
        elif line.startswith("数据示例"):
            # Skip the "数据示例" and opening backticks
            i += 1
            example_data, i = extract_data_example(lines, i)
            continue

        i += 1

    return APIEntry(
        name=name,
        title=title,
        url=url,
        description=description,
        limit=limit,
        input_params=input_params,
        output_params=output_params,
        example_code=example_code,
        example_data=example_data,
        context=context.copy(),
    )


class AKShareDocParser:
    """Main parser for AKShare documentation."""

    def __init__(self, input_file: Path):
        self.input_file = input_file
        self.root = Section(level=0, name="root")
        self.api_entries: list[APIEntry] = []
        self.section_stack: list[Section] = [self.root]
        self.api_by_name: dict[str, APIEntry] = {}
        self.api_by_category: dict[str, list[APIEntry]] = defaultdict(list)

    def parse(self) -> None:
        """Parse the entire documentation file."""
        content = self.input_file.read_text(encoding="utf-8")
        lines = content.split("\n")

        # Reset for parsing
        self.root = Section(level=0, name="root")
        self.section_stack = [self.root]

        # Single pass: build sections and parse APIs together
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Check for section headers
            if line.startswith("#") and not line.startswith("```"):
                match = re.match(r"^#+", line)
                if match:
                    level = len(match.group(0))
                else:
                    level = 1
                name = re.sub(r"^#+\s*", "", line).strip()

                # Skip empty names or just URL references
                if not name or name.startswith("["):
                    i += 1
                    continue

                # Create new section
                section = Section(level=level, name=name)

                # Update stack
                while self.section_stack and self.section_stack[-1].level >= level:
                    self.section_stack.pop()

                if self.section_stack:
                    section.parent = self.section_stack[-1]
                    section.parent.children.append(section)

                self.section_stack.append(section)

            # Look for "接口:" line (API entries)
            elif line.startswith("接口:"):
                api_name = line.replace("接口:", "").strip()
                if api_name:
                    # Get context from current section stack
                    section_context = self._get_context_from_stack()

                    # Parse the full API entry
                    api = parse_api_entry_at(lines, i, section_context)
                    if api:
                        self.api_entries.append(api)
                        self.api_by_name[api.name] = api
                        self.api_by_category[api.context.get("path", "")].append(api)

                        # Add to current section
                        if self.section_stack:
                            self.section_stack[-1].apis.append(api)

            i += 1

    def _get_context_from_stack(self) -> dict[str, Any]:
        """Get context from current section stack."""
        levels: dict[int, str] = {}
        stack_parts: list[tuple[int, str]] = []

        for section in self.section_stack:
            if section.level > 0:  # Skip root
                levels[section.level] = section.name
                stack_parts.append((section.level, section.name))

        # Build path
        path_parts = [n for _, n in stack_parts]
        path = " > ".join(path_parts)

        return {
            "path": path,
            "level_1": levels.get(2, ""),
            "level_2": levels.get(3, ""),
            "level_3": levels.get(4, ""),
            "level_4": levels.get(5, ""),
            "level_5": levels.get(6, ""),
        }

    def to_json_index(self) -> dict[str, Any]:
        """Convert to JSON index structure."""

        def section_to_dict(section: Section) -> dict[str, Any]:
            return {
                "name": section.name,
                "level": section.level,
                "path": section.path,
                "children": [section_to_dict(c) for c in section.children],
                "apis": [
                    {
                        "name": api.name,
                        "title": api.title,
                        "description": api.description,
                        "url": api.url,
                        "limit": api.limit,
                        "input_params": [
                            {"name": p.name, "type": p.type_, "description": p.description}
                            for p in api.input_params
                        ],
                        "output_params": [
                            {"name": p.name, "type": p.type_, "description": p.description}
                            for p in api.output_params
                        ],
                    }
                    for api in section.apis
                ],
            }

        return {
            "metadata": {
                "total_apis": len(self.api_entries),
                "total_sections": sum(1 for _ in self._flatten_sections(self.root.children)),
            },
            "root": section_to_dict(self.root),
            "api_index": {
                name: {
                    "title": api.title,
                    "description": api.description,
                    "url": api.url,
                    "path": api.context.get("path", ""),
                }
                for name, api in self.api_by_name.items()
            },
            "category_index": {
                path: [api.name for api in apis] for path, apis in self.api_by_category.items()
            },
        }

    def _flatten_sections(self, sections: list[Section]) -> list[Section]:
        """Flatten section tree."""
        result = []
        for s in sections:
            result.append(s)
            result.extend(self._flatten_sections(s.children))
        return result


def main() -> None:
    """Main entry point."""
    script_dir = Path(__file__).parent
    input_file = script_dir / "akshare_stock.md"
    output_dir = script_dir / "akshare_parsed"

    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        return

    print(f"Parsing {input_file.name}...")

    # Parse documentation
    parser = AKShareDocParser(input_file)
    parser.parse()

    print(f"Found {len(parser.api_entries)} API entries")

    # Create output directory
    output_dir.mkdir(exist_ok=True)

    # Generate JSON index
    json_file = output_dir / "index.json"
    json_data = parser.to_json_index()
    json_file.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Created JSON index: {json_file}")
    print(f"\nOutput written to: {output_dir}/")


if __name__ == "__main__":
    main()

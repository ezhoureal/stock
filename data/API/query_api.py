#!/usr/bin/env python3
"""
Query interface for AKShare API documentation using JSON index.
Can be used as a standalone script or called by the /akshare skill.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

INDEX_FILE = Path(__file__).parent / "akshare_parsed" / "index.json"


def load_index() -> dict:
    """Load the JSON index."""
    if not INDEX_FILE.exists():
        print(f"Error: Index file not found: {INDEX_FILE}")
        print("Run parse_akshare_doc.py first to generate the index.")
        sys.exit(1)

    with open(INDEX_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_api_info(index: dict, api_name: str) -> str:
    """Get detailed API information including parameters."""
    # Find API in api_index or by searching the tree
    if api_name in index["api_index"]:
        basic_info = index["api_index"][api_name]
    else:
        # Try to find in the tree
        for cat in index["category_index"].values():
            if api_name in cat:
                # Found in category, get basic info from tree
                basic_info = {"title": "", "description": "", "url": "", "path": ""}
                break
        else:
            return f"API '{api_name}' not found."

    # Get full details from tree
    def find_api_in_tree(section: dict, name: str) -> dict | None:
        if "apis" in section:
            for api in section["apis"]:
                if api["name"] == name:
                    return api
        if "children" in section:
            for child in section["children"]:
                result = find_api_in_tree(child, name)
                if result:
                    return result
        return None

    api_details = find_api_in_tree(index["root"], api_name)
    if not api_details:
        return f"API '{api_name}' found but details unavailable."

    # Format output
    output = f"**{api_name}**\n"
    output += f"- **Description**: {api_details.get('description', basic_info['description'])}\n"
    output += f"- **URL**: {api_details.get('url', basic_info['url'])}\n"
    output += f"- **Category**: {basic_info['path']}\n"

    if api_details.get("input_params"):
        output += "\n**Input Parameters:**\n"
        output += "| Name | Type | Description |\n"
        output += "|------|------|-------------|\n"
        for p in api_details["input_params"]:
            output += f"| {p['name']} | {p['type']} | {p['description']} |\n"

    if api_details.get("output_params"):
        output += "\n**Output Parameters:**\n"
        output += "| Name | Type | Description |\n"
        output += "|------|------|-------------|\n"
        for p in api_details["output_params"][:10]:  # Limit output params
            output += f"| {p['name']} | {p['type']} | {p['description']} |\n"
        if len(api_details["output_params"]) > 10:
            output += f"| ... | ... | ({len(api_details['output_params']) - 10} more) |\n"

    return output


def search_apis(index: dict, keyword: str) -> str:
    """Search APIs by keyword."""
    results = [
        (name, info)
        for name, info in index["api_index"].items()
        if keyword.lower() in name.lower() or keyword in info["description"]
    ]

    if not results:
        return f"No APIs found matching '{keyword}'"

    output = f"Found {len(results)} APIs matching '{keyword}':\n\n"
    for name, info in results[:10]:
        output += f"- **{name}**: {info['description'][:80]}...\n"
    if len(results) > 10:
        output += f"\n... and {len(results) - 10} more"
    return output


def list_categories(index: dict) -> str:
    """List all API categories."""
    output = "AKShare API Categories:\n\n"
    for cat, apis in index["category_index"].items():
        output += f"- **{cat}**: {len(apis)} APIs\n"
    return output


def main() -> None:
    """Main entry point."""
    index = load_index()

    if len(sys.argv) > 1:
        keyword = sys.argv[1]
        # Check if it's an exact API name match
        if keyword in index["api_index"]:
            print(get_api_info(index, keyword))
        else:
            print(search_apis(index, keyword))
    else:
        # Show overview
        print(list_categories(index))


if __name__ == "__main__":
    main()

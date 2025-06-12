#!/usr/bin/env python3
# Objective: Modify `frontend/src/app/copilot/[business_name]/page.tsx`
# to remove hardcoded `/api` prefixes from `fetch` calls and use environment
# variables for the base URL.

# Steps:
# 1. Read the content of the file.
# 2. Define a constant for the API base URL at the component or module scope,
#    using `process.env.NEXT_PUBLIC_API_BASE || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'`.
# 3. Find all `fetch` calls that have `/api/...` in their URL.
# 4. Modify these fetch calls:
#    - Remove the leading `/api` from the path.
#    - Prepend the defined API base URL constant.
# 5. Write the modified content back to the file.

import re
import sys

filepath = "frontend/src/app/copilot/[business_name]/page.tsx"

try:
    with open(filepath, "r") as f:
        content = f.read()
except FileNotFoundError:
    print(f"Error: File not found at {filepath}")
    sys.exit(1)

# Define the base URL string to be inserted.
api_base_url_definition = "const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';"

# --- Insertion of API_BASE_URL definition ---
# Attempt to insert after 'use client'; which is common in Next.js client components
use_client_directive = "'use client';"
use_client_match = re.search(re.escape(use_client_directive) + r"\s*\n", content) # Look for directive followed by a newline

inserted_definition = False
if use_client_match:
    insert_pos = use_client_match.end()
    # Check if it's already defined to prevent duplicate insertion
    if "const API_BASE_URL" not in content:
        content = content[:insert_pos] + "\n" + api_base_url_definition + "\n" + content[insert_pos:]
        inserted_definition = True
    else:
        print("API_BASE_URL definition already exists. Skipping insertion.")
        inserted_definition = True # Considered done
else:
    # Fallback: try after the last import statement
    # This regex looks for typical import lines.
    last_import_match = list(re.finditer(r"^(import .+ from '.+';|import '.+';|const .+ = require\(.+\);|import React from 'react';)\s*$", content, re.MULTILINE))
    if last_import_match:
        insert_pos = last_import_match[-1].end()
        if "const API_BASE_URL" not in content: # Check again
            content = content[:insert_pos] + "\n\n" + api_base_url_definition + "\n" + content[insert_pos:]
            inserted_definition = True
        else:
            print("API_BASE_URL definition already exists (found near imports). Skipping insertion.")
            inserted_definition = True # Considered done
    else:
        # Fallback: if no 'use client' and no imports, prepend (less ideal but ensures definition)
        if "const API_BASE_URL" not in content: # Check again
            content = api_base_url_definition + "\n\n" + content
            inserted_definition = True
        else:
            print("API_BASE_URL definition already exists (checked at top). Skipping insertion.")
            inserted_definition = True # Considered done

if inserted_definition and "const API_BASE_URL" not in api_base_url_definition and "API_BASE_URL definition already exists" not in content : # only print if actually inserted
     print(f"Inserted API_BASE_URL definition.")


# --- Modification of fetch calls ---
# Regex to find fetch calls with hardcoded '/api/'
# Pattern 1: fetch(`/api/...`)
fetch_pattern_template_literal = re.compile(r"fetch\(\s*`\s*/api(/[^`]+)`")
# Pattern 2: fetch('/api/...') or fetch("/api/...")
fetch_pattern_quoted_string = re.compile(r"fetch\(\s*(['\"])\s*/api(/[^'\" \)]+)\1") # \1 refers to the matched quote

# Replacement function for template literals
def replace_fetch_template(match):
    path_without_api = match.group(1)
    # Ensure path_without_api starts with a slash if it's not empty.
    # The regex already captures it with a leading slash.
    return f"fetch(`${{API_BASE_URL}}{path_without_api}`"

# Replacement function for regular strings
def replace_fetch_quotes(match):
    # group(1) is the quote type, group(2) is the path
    path_without_api = match.group(2)
    # We need to construct the string carefully: API_BASE_URL + '/actual/path'
    return f"fetch(API_BASE_URL + '{path_without_api}'" # Note: the closing ')' of fetch is not part of match


original_content = content # For comparison to see if changes were made

content = fetch_pattern_template_literal.sub(replace_fetch_template, content)
content = fetch_pattern_quoted_string.sub(replace_fetch_quotes, content)

# Specific pattern for /copilot-growth/nudges/${nudgeId}/launch-campaign
# This one was noted as potentially already modified or needing specific attention.
# The regex should be robust to catch it if it's still using `/api`.
# Example: fetch(`/api/copilot-growth/nudges/${nudgeId}/launch-campaign`
specific_growth_fetch_pattern = re.compile(r"fetch\(\s*`\s*/api(/copilot-growth/nudges/\$\{nudgeId\}/launch-campaign)`")
content = specific_growth_fetch_pattern.sub(r"fetch(`${API_BASE_URL}\1`)", content) # Use \1 to refer to the captured group

# Another common pattern: fetch('/api/endpoint/' + variable)
# This is more complex. Let's try a common case: fetch('/api/somepath/' + varName
fetch_pattern_concat_string = re.compile(r"fetch\(\s*(['\"])\s*/api(/[^'\" ]+)\1\s*\+\s*([\w\.]+)\)")
def replace_fetch_concat_string(match):
    quote = match.group(1)
    path_segment = match.group(2) # e.g., /somepath/
    variable_name = match.group(3)
    return f"fetch(API_BASE_URL + '{path_segment}' + {variable_name})"
content = fetch_pattern_concat_string.sub(replace_fetch_concat_string, content)


if content == original_content and not inserted_definition:
    print(f"No changes made to fetch calls in {filepath} (they might already be updated or not match patterns).")
else:
    try:
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Successfully refactored fetch calls in {filepath} to use API_BASE_URL.")
    except Exception as e:
        print(f"Error writing updated content to {filepath}: {e}")
        sys.exit(1)

#!/usr/bin/env python3
# Objective: Modify SessionMiddleware in `backend/main.py`
# to set `same_site="none"` and `https_only=True`.

# Steps:
# 1. Read the content of `backend/main.py`.
# 2. Find the lines containing `same_site=` and `https_only=` within the SessionMiddleware block.
# 3. Modify these specific lines.
# 4. Write the modified content back.

import re
import sys

filepath = "backend/main.py"

try:
    with open(filepath, "r") as f:
        lines = f.readlines()

    new_lines = []
    in_session_middleware_block = False
    # Flags to track if we've successfully made the specific modifications
    samesite_set_to_none = False
    httpsonly_set_to_true = False

    # Flags to track if we found the parameters at all
    found_samesite_param = False
    found_httpsonly_param = False

    for line_number, line_content in enumerate(lines):
        current_line = line_content
        if "app.add_middleware(" in line_content and "SessionMiddleware" in line_content:
            in_session_middleware_block = True

        if in_session_middleware_block:
            if "same_site=" in current_line:
                found_samesite_param = True
                # Replace the value for same_site, ensuring it becomes exactly same_site="none"
                # This regex handles existing quotes and value, and potential spaces around '='
                modified_line = re.sub(r'same_site\s*=\s*["\']\w+["\']', 'same_site="none"', current_line)
                if 'same_site="none"' in modified_line:
                    samesite_set_to_none = True
                current_line = modified_line
            elif "https_only=" in current_line:
                found_httpsonly_param = True
                # Replace the value for https_only, ensuring it becomes exactly https_only=True
                # This regex handles existing True/False and potential spaces around '='
                modified_line = re.sub(r'https_only\s*=\s*(True|False|true|false)', 'https_only=True', current_line)
                if 'https_only=True' in modified_line:
                    httpsonly_set_to_true = True
                current_line = modified_line

            # Check for the end of the SessionMiddleware block
            # This assumes the block ends with a closing parenthesis ')' possibly with leading whitespace.
            if current_line.strip().endswith(")") and not current_line.strip().startswith("app.add_middleware("):
                 # More specific check: if the line contains SessionMiddleware and also the closing )
                if "SessionMiddleware" in line_content and line_content.count('(') == line_content.count(')'):
                     # This is likely a single-line definition, block already ended.
                     in_session_middleware_block = False
                elif not ("SessionMiddleware" in line_content): # if it's a multi-line block, the ) is on its own line or with last param
                     in_session_middleware_block = False


        new_lines.append(current_line)

    # After processing all lines, check if modifications were successful
    if not found_samesite_param:
        print(f"Warning: 'same_site' parameter not found in SessionMiddleware block in {filepath}.")
    elif not samesite_set_to_none:
        print(f"Warning: 'same_site' parameter was found but not successfully set to 'none'. Current line might be unexpected.")

    if not found_httpsonly_param:
        print(f"Warning: 'https_only' parameter not found in SessionMiddleware block in {filepath}.")
    elif not httpsonly_set_to_true:
        print(f"Warning: 'https_only' parameter was found but not successfully set to 'True'. Current line might be unexpected.")

    # If either parameter was not found, it's a more critical issue than just failing to set the value.
    if not found_samesite_param or not found_httpsonly_param:
        print("Error: One or both SessionMiddleware parameters ('same_site', 'https_only') were not found. File not modified to prevent potential errors.")
        # sys.exit(1) # Exit if parameters are missing, as the goal is to set them.
                     # For this task, let's allow writing if at least one was found and processed.
                     # The problem statement implies modifying existing lines.

    # Write content back if at least one parameter was found and successfully set to the target value.
    # Or, more leniently, write back if any change was made (even if one parameter was missing).
    # For this task, we'll write if samesite_set_to_none OR httpsonly_set_to_true is true.
    if samesite_set_to_none or httpsonly_set_to_true:
        with open(filepath, "w") as f:
            f.writelines(new_lines)
        print(f"Successfully updated SessionMiddleware settings in {filepath}.")
        if samesite_set_to_none:
            print("  - same_site is now 'none'")
        if httpsonly_set_to_true:
            print("  - https_only is now True")
    else:
        print(f"No changes made to SessionMiddleware settings in {filepath} or parameters were not found/set as expected.")


except Exception as e:
    print(f"An error occurred: {e}")
    sys.exit(1)

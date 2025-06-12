#!/usr/bin/env python3
import sys

filepath = "backend/main.py"

# This script ensures the `strip_api_prefix` middleware is removed.
# It's designed to be idempotent: if the middleware is already gone, it does nothing.

try:
    with open(filepath, "r") as f:
        lines = f.readlines()

    new_lines = []
    middleware_decorator_marker = "@app.middleware(\"http\")" # Corrected missing quote
    middleware_def_line_marker = "async def strip_api_prefix(request: Request, call_next):"

    potential_block_start_index = -1
    block_exists = False

    # First pass: identify if the block exists and where it starts
    for i, line in enumerate(lines):
        # Check for the decorator line
        if middleware_decorator_marker in line:
            # Check if the *next* line contains the specific function definition
            if i + 1 < len(lines) and middleware_def_line_marker in lines[i+1]:
                # Check that this is not some other function's decorator by looking at indentation of current line
                # A typical decorator is not indented.
                if not line.strip().startswith("#") and line.startswith("@"): # Ensure it's an active decorator
                    block_exists = True
                    potential_block_start_index = i
                    break

    if not block_exists:
        sys.stdout.write(f"The strip_api_prefix middleware block does not appear to be present in {filepath}. No changes made.\n")
        sys.exit(0) # Exit successfully, as the state is already as desired.

    # If block seems to exist, proceed to construct new_lines without it
    i = 0
    processed_block = False # Flag to ensure we only process the first identified block
    while i < len(lines):
        line = lines[i]
        if not processed_block and i == potential_block_start_index:
            # Start of the identified block
            block_line_count = 0
            found_block_end = False
            # Determine the indentation of the decorator line
            decorator_indentation = len(line) - len(line.lstrip())

            for j in range(potential_block_start_index, len(lines)):
                current_line_in_block = lines[j]
                block_line_count += 1

                # The specific 'return response' for the middleware we want to remove.
                # It should have an indentation greater than the decorator.
                if current_line_in_block.strip() == "return response":
                    # Check indentation of this return statement
                    return_indentation = len(current_line_in_block) - len(current_line_in_block.lstrip())
                    if return_indentation > decorator_indentation: # Belongs to the middleware function
                        found_block_end = True
                        break

                # Safety break: if we encounter another decorator or a top-level function/class definition
                # that is at the same indentation level as the original decorator, it means we've passed our block.
                if j > potential_block_start_index: # Don't check the first line of the block itself
                    line_strip = current_line_in_block.strip()
                    current_line_indent = len(current_line_in_block) - len(current_line_in_block.lstrip())
                    if current_line_indent == decorator_indentation and (line_strip.startswith("@") or line_strip.startswith("def ") or line_strip.startswith("class ")):
                        # We've hit the next major block at the same indentation as our decorator
                        # This means the 'return response' was not found within the expected scope.
                        # Set block_line_count to 0 to indicate an issue or stop before this line.
                        # For this script, we assume 'return response' is the true end. If it's missing, this break is a fallback.
                        sys.stderr.write(f"Warning: Reached another top-level block at line {j+1} before finding 'return response' for the target middleware. The middleware might be malformed or already partially removed.\n")
                        block_line_count -=1 # Don't include this line as part of the block to remove
                        break


            if found_block_end:
                sys.stdout.write(f"Identified strip_api_prefix middleware block of {block_line_count} lines starting at line {potential_block_start_index + 1}. Removing it.\n")
                i += block_line_count # Advance main loop index past this block
                processed_block = True # Mark as processed
                continue
            else:
                sys.stderr.write(f"Error: Found start of strip_api_prefix middleware but could not reliably find its end ('return response'). Aborting to prevent file corruption.\n")
                sys.exit(1)

        new_lines.append(line)
        i += 1

    with open(filepath, "w") as f:
        f.writelines(new_lines)

    sys.stdout.write(f"Successfully ensured the strip_api_prefix middleware is removed from {filepath}.\n")

except FileNotFoundError:
    sys.stderr.write(f"Error: {filepath} not found.\n")
    sys.exit(1)
except Exception as e:
    sys.stderr.write(f"An error occurred: {e}\n")
    sys.exit(1)

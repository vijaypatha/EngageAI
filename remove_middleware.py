#!/usr/bin/env python3
import sys

filepath = "backend/main.py"

# The exact lines of the middleware to be removed.
# Based on the version of main.py we are currently working with (with enhanced logging).
# It starts with the decorator and ends with the 'return response' line of that function.

# It is:
# @app.middleware("http")
# async def strip_api_prefix(request: Request, call_next):
#     logger.info(f"[strip_api_prefix] Received request for original_url_path: {request.url.path}, current_scope_path: {request.scope.get('path')}")
#     original_url_path = request.url.path # Unmodified URL path
#     current_scope_path = request.scope.get('path', original_url_path) # Path that router will see, possibly modified by other middleware
#
#     final_scope_path_for_router = current_scope_path # Assume no change initially
#
#     if current_scope_path.startswith("/api"):
#         new_path_segment = current_scope_path[4:] # Remove '/api'
#
#         if not new_path_segment: # Original scope path was "/api" or "/api/"
#             final_scope_path_for_router = "/"
#         elif not new_path_segment.startswith("/"):
#             final_scope_path_for_router = "/" + new_path_segment
#         else:
#             final_scope_path_for_router = new_path_segment
#
#         request.scope['path'] = final_scope_path_for_router
#         logger.info(f"[strip_api_prefix] Original URL path: {original_url_path}. Scope path before strip: {current_scope_path}. Stripped scope path for router to: {final_scope_path_for_router}")
#     else:
#         logger.info(f"[strip_api_prefix] Scope path {current_scope_path} (from URL path {original_url_path}) does not start with /api, no modification by this middleware.")
#
#     response = await call_next(request)
#     # Optional: log response status code here if needed
#     # logger.info(f"[strip_api_prefix] Responding to {original_url_path}. Router saw {final_scope_path_for_router}. Status: {response.status_code}")
#     return response

try:
    with open(filepath, "r") as f:
        lines = f.readlines()

    new_lines = []
    in_middleware_block = False
    # Ensure exact match for decorator to avoid accidental matches if other decorators exist
    middleware_decorator_line = "@app.middleware(\"http\")\n"
    middleware_def_line_part = "async def strip_api_prefix(request: Request, call_next):"

    # More specific end marker for the version of the middleware with logging:
    # The last line is '    return response\n'
    # The line before it, in the logged version, is commented out:
    # '    # logger.info(f"[strip_api_prefix] Responding to {original_url_path}. Router saw {final_scope_path_for_router}. Status: {response.status_code}")\n'
    # So, we search for 'return response' and assume it's the end of our target block
    # when `in_middleware_block` is true.

    i = 0
    while i < len(lines):
        line = lines[i]
        if not in_middleware_block and line == middleware_decorator_line:
            # Check if the next line is the def
            if i + 1 < len(lines) and middleware_def_line_part in lines[i+1]:
                in_middleware_block = True
                # We are skipping the decorator line (current 'line') and the def line (lines[i+1])
                i += 2 # Advance past decorator and def
                continue
            else: # Decorator found, but not our specific function
                new_lines.append(line)
                i += 1
        elif in_middleware_block:
            # If we are in the block, check for its end.
            # The specific end for the enhanced logging version is the line "    return response\n"
            if line.strip() == "return response":
                in_middleware_block = False # End of block
                i += 1 # Skip this return line
                # Check for a blank line that might have been part of the original spacing
                # and remove it if the next line is "# Configure CORS"
                if i < len(lines) and lines[i].strip() == "" and (i + 1 < len(lines) and lines[i+1].startswith("# Configure CORS")):
                    i +=1 # skip blank line
                continue
            i += 1 # Skip lines within the middleware block
        else: # Not in block and not starting a block
            new_lines.append(line)
            i += 1

    if in_middleware_block: # Safety check
        sys.stderr.write(f"Error: Middleware block end not properly detected. File not modified to prevent corruption.\n")
        sys.exit(1)

    with open(filepath, "w") as f:
        f.writelines(new_lines)

    sys.stdout.write(f"Successfully removed the strip_api_prefix middleware from {filepath}.\n")

except FileNotFoundError:
    sys.stderr.write(f"Error: File not found at {filepath}\n")
    sys.exit(1)
except Exception as e:
    sys.stderr.write(f"An error occurred: {e}\n")
    sys.exit(1)

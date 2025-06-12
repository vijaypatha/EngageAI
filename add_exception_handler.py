#!/usr/bin/env python3
import logging # Not used in this script, but often good practice
import sys

filepath = "backend/main.py"

# This is the Python code for the new exception handler.
# It needs to be correctly indented when inserted into the target file.
# Using a raw triple-quoted string and then handling indentation during insertion.
new_handler_definition_str = """
@app.exception_handler(HTTPException)
async def custom_http_exception_logger_handler(request: Request, exc: HTTPException):
    # Ensure logger is available (it's global in main.py)
    # import logging
    # logger = logging.getLogger(__name__) # Redundant if logger is truly global and already set up

    log_message_prefix = f"[CustomHTTPExceptionHandler] Path: {request.method} {request.url.path}"

    if exc.status_code == 404:
        logger.warning(f"{log_message_prefix} - Result: 404 Not Found. Detail: {exc.detail}")
        # For 404s, it's often useful to see headers to debug proxy issues, content negotiation, etc.
        logger.debug(f"{log_message_prefix} - Request Headers for 404: {{dict(request.headers)}}")
    else:
        # Log other HTTPExceptions as errors, as they might indicate server-side issues
        # or bad client requests that are not just 'not found'.
        logger.error(f"{log_message_prefix} - Result: HTTPException Status={exc.status_code}, Detail: {exc.detail}")
        logger.debug(f"{log_message_prefix} - Request Headers: {{dict(request.headers)}}")

    # Return a JSON response consistent with FastAPI's default for HTTPExceptions
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail if exc.detail is not None else "An HTTP error occurred."}, # Ensure detail is not None
        headers=getattr(exc, "headers", None) # Preserve headers from original exception if any
    )
"""

# We need to ensure that FastAPI, Request, HTTPException, JSONResponse, and logger are available
# in the scope where this handler is defined in main.py.
# FastAPI, Request, HTTPException, JSONResponse are imported at the top of main.py.
# logger is defined globally as `logger = logging.getLogger(__name__)`.

try:
    with open(filepath, "r") as f:
        content_lines = f.readlines()

    # Determine the insertion point: before the generic `@app.exception_handler(Exception)`
    # or, if that's not found, before `if __name__ == "__main__":`.

    # Marker for the generic Exception handler
    generic_handler_marker = "@app.exception_handler(Exception)"
    # Marker for the main execution block
    main_block_marker = "if __name__ == \"__main__\":"

    insert_at_line_index = -1

    # First, try to find the generic Exception handler
    for i, line_content in enumerate(content_lines):
        if generic_handler_marker in line_content:
            insert_at_line_index = i
            break

    # If not found, try to find the main block marker
    if insert_at_line_index == -1:
        for i, line_content in enumerate(content_lines):
            if main_block_marker in line_content:
                insert_at_line_index = i
                break

    if insert_at_line_index == -1:
        sys.stderr.write(f"Error: Could not find a suitable insertion point in {filepath}.\n")
        sys.exit(1)

    # Prepare the new handler code lines, ensuring they have no leading/trailing whitespace issues from the string def
    new_handler_lines = [line + "\n" for line in new_handler_definition_str.strip().split('\n')]

    # Add an extra newline after the handler block for separation
    new_handler_lines.append("\n")

    # Insert the new handler lines into the content
    modified_content_lines = content_lines[:insert_at_line_index] + new_handler_lines + content_lines[insert_at_line_index:]

    with open(filepath, "w") as f:
        f.write("".join(modified_content_lines))

    sys.stdout.write(f"Successfully added custom HTTPException logging handler to {filepath}.\n")

except Exception as e:
    sys.stderr.write(f"An error occurred: {e}\n")
    sys.exit(1)

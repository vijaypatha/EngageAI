# Objective: Modify `render.yaml` to add `--root-path /api` to the uvicorn start command.
# Steps:
# 1. Read the content of `backend/render.yaml`.
# 2. Find the line containing `startCommand: uvicorn main:app ...`.
# 3. Append `--root-path /api` to this command.
# 4. Write the modified content back to `backend/render.yaml`.

import ruamel.yaml
import sys # Import sys for exit and print

yaml_file_path = "backend/render.yaml" # Path to the render.yaml file in the project
yaml = ruamel.yaml.YAML()
yaml.preserve_quotes = True # Preserve quotes if any
yaml.indent(mapping=2, sequence=4, offset=2) # Standard YAML indentation

try:
    with open(yaml_file_path, 'r') as f:
        data = yaml.load(f)
except FileNotFoundError:
    print(f"Error: {yaml_file_path} not found.")
    sys.exit(1)
except Exception as e:
    print(f"Error loading {yaml_file_path}: {e}")
    sys.exit(1)


found_command_and_updated = False
service_found = False

if 'services' in data and isinstance(data['services'], list):
    for service in data['services']:
        if isinstance(service, dict) and service.get('name') == 'engageai-backend': # Target service name
            service_found = True
            if 'startCommand' in service:
                current_command = service['startCommand']
                if 'uvicorn main:app' in current_command: # Check if it's the uvicorn command for main:app
                    if '--root-path /api' not in current_command:
                        service['startCommand'] = current_command.strip() + " --root-path /api"
                        found_command_and_updated = True
                        print(f"Successfully updated startCommand in {yaml_file_path} to include --root-path /api.")
                    else:
                        print("Warning: --root-path /api already present in startCommand.")
                        found_command_and_updated = True # Already correct, consider it done
                    break # Exit loop once the target service and command are processed
            else:
                print(f"Error: 'startCommand' not found in service 'engageai-backend'.")
                # If startCommand is missing, we might not want to proceed or try to add it.
                # For now, we'll just report and exit.
                sys.exit(1) # Or handle as a non-fatal error if appropriate

if not service_found:
    print(f"Error: Service 'engageai-backend' not found in {yaml_file_path}.")
    sys.exit(1)

if not found_command_and_updated and service_found:
    # This case means the service was found, but the command wasn't what we expected (e.g., not uvicorn or not main:app)
    # or it was already updated (which is handled by the print and `found_command_and_updated = True` inside the loop)
    # So, if it's not updated AND the service was found, it means the specific command wasn't there.
    print(f"Error: Could not find or update the expected 'uvicorn main:app ...' startCommand in service 'engageai-backend'. Current command might be different or already handled.")
    # Depending on strictness, this could be sys.exit(1)
    # For now, let it pass if it was just a warning about already being present.

if service_found and any(service.get('name') == 'engageai-backend' and '--root-path /api' in service.get('startCommand','') for service in data.get('services',[])):
    try:
        with open(yaml_file_path, 'w') as f:
            yaml.dump(data, f)
        # Confirmation message is now printed only if an update happened or it was already correct.
        # If an error occurred before this point, sys.exit would have been called.
    except Exception as e:
        print(f"Error writing updated content to {yaml_file_path}: {e}")
        sys.exit(1)
else:
    # This else implies that either the service wasn't found, or if it was, the command wasn't updated.
    # The specific error messages above should provide more context.
    # If we reach here without found_command_and_updated being true (and no sys.exit yet), it's an issue.
    if not found_command_and_updated: # Re-check because the previous block might not have exited.
      print("Final check: startCommand was not updated as expected, and no explicit error led to exit. File not saved.")
      sys.exit(1)

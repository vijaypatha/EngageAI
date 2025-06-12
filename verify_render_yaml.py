# Objective: Ensure `render.yaml` includes `--root-path /api` in the uvicorn start command.
# This is a re-application or verification step.
# Steps:
# 1. Read `backend/render.yaml`.
# 2. Check if `startCommand` for `engageai-backend` service contains `--root-path /api`.
# 3. If not, add it. If it's already correct, confirm.
# 4. Write back if changes were made.

import ruamel.yaml
import sys

yaml_file_path = "backend/render.yaml"
yaml = ruamel.yaml.YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2) # For consistent output if changed

try:
    with open(yaml_file_path, 'r') as f:
        data = yaml.load(f)
except FileNotFoundError:
    print(f"Error: {yaml_file_path} not found.")
    sys.exit(1)
except Exception as e:
    print(f"Error reading or parsing {yaml_file_path}: {e}")
    sys.exit(1)

modified = False
found_service = False
if 'services' in data and isinstance(data['services'], list):
    for service in data['services']:
        if isinstance(service, dict) and service.get('name') == 'engageai-backend':
            found_service = True
            if 'startCommand' in service:
                current_command = service['startCommand']
                if 'uvicorn main:app' in current_command: # Target the specific command
                    expected_addition = "--root-path /api"
                    # Check if it's already there as a distinct word/arg
                    command_parts = current_command.split()
                    is_present = False
                    for i, part in enumerate(command_parts):
                        if part == "--root-path" and i + 1 < len(command_parts) and command_parts[i+1] == "/api":
                            is_present = True
                            break
                        # Also handle if it's joined like --root-path=/api
                        if part.startswith("--root-path=") and part.split("=")[1] == "/api":
                            is_present = True
                            break

                    if not is_present:
                        # Add it, trying to be careful about extra spaces
                        service['startCommand'] = current_command.rstrip() + " " + expected_addition
                        modified = True
                        print(f"Modified startCommand to: {service['startCommand']}")
                    else:
                        print(f"startCommand already contains {expected_addition}. No changes needed to command string.")
                        # modified remains False, as no change was made by this script run
                else:
                    print(f"Error: 'uvicorn main:app' not found in startCommand: {current_command} for service 'engageai-backend'.")
                    sys.exit(1) # Critical error if structure is not as expected
            else:
                print(f"Error: 'startCommand' not found in service 'engageai-backend'.")
                sys.exit(1) # Critical error
            break # Found and processed the service

if not found_service:
    print(f"Error: Service 'engageai-backend' not found in {yaml_file_path}.")
    sys.exit(1)

if modified:
    try:
        with open(yaml_file_path, 'w') as f:
            yaml.dump(data, f)
        print(f"Successfully updated startCommand in {yaml_file_path}.")
    except Exception as e:
        print(f"Error writing updated {yaml_file_path}: {e}")
        sys.exit(1)
else:
    # This message is printed if the file was loaded, service found, command checked, and no *modifications* were made by this script.
    print(f"No modifications were necessary to {yaml_file_path} regarding --root-path /api during this run.")

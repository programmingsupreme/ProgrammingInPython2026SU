import os
import platform

# List all files and directories
print("Current directory contents:", os.listdir('.'))

# Create a new directory
os.mkdir('test_dir')
print("Created 'test_dir':", 'test_dir' in os.listdir('.'))

# Rename a file
with open('old_name.txt', 'w') as f:
    f.write('Sample text')
os.rename('old_name.txt', 'new_name.txt')
print("Renamed file:", 'new_name.txt' in os.listdir('.'))

# Set and get file permissions (only for Unix-based systems)
if os.name == 'posix':
    os.chmod('new_name.txt', 0o644)  # Set file permissions to rw-r--r--
    file_permissions = oct(os.stat('new_name.txt').st_mode)[-3:]
    print(f"File permissions for 'new_name.txt': {file_permissions}")
else:
    print("File permissions setting is not supported on this operating system")

# Additional OS-specific information
if platform.system() == "Windows":
    print("Running on Windows")
elif platform.system() == "Linux":
    print("Running on Linux")
elif platform.system() == "Darwin":
    print("Running on macOS")
else:
    print("Unknown operating system")

print("Script executed successfully.")

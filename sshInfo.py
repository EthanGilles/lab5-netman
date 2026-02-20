try:
    import json
except ImportError:
    print("Missing the library 'json'.")
    exit(1)

try:
    import os
except ImportError:
    print("Missing the library 'os'.")
    exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("Missing library 'python-dotenv'.")
    exit(1)


def load_ssh_info():
    load_dotenv()
    # Default to local sshInfo.json if env var is not provided
    info_file = os.getenv("SSH_INFO_FILE", "sshInfo.json")

    if not os.path.exists(info_file):
        raise FileNotFoundError(f"{info_file} not found, check that the file exists at the path entered")

    try: 
        with open(info_file, "r") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        raise ValueError(f"{info_file} contains invalid JSON!")

    # Return routers list (empty list if key missing)
    return data.get("routers", [])

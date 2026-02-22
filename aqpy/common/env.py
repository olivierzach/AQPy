import os


def env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default

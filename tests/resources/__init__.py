import os.path


def resource_path(*paths: str) -> str | bytes:
    """Return the absolute path of a file in this module constructed from the relative path components."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), *paths))


def resource_content(*paths: str) -> str:
    """Return the contents of a file in this module constructed from the relative path components."""
    with open(resource_path(*paths)) as f:
        return f.read()

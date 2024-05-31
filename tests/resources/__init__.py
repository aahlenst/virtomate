import os.path


def fixture(name: str) -> str:
    """Read and return the contents of the fixture with the given name."""
    path = os.path.join(os.path.dirname(__file__), "fixtures", name)
    with open(path) as f:
        return f.read()


def expectation(name: str) -> str:
    """Read and return the contents of the expectation with the given name."""
    path = os.path.join(os.path.dirname(__file__), "expectations", name)
    with open(path) as f:
        return f.read()

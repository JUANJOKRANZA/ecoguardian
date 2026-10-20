"""Install one shared Streamlit simulator before app modules are imported by tests."""
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# The application is imported by several test modules during collection. Install the simulator
# once here so eco.pages and app.py keep references to the same object throughout the suite.
try:
    import streamlit  # noqa: F401
except ImportError:
    from fake_streamlit import install
    install()

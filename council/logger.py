"""Logging utility for IdeaCouncil."""

import logging
import sys

# Create a module-level logger
logger = logging.getLogger("ideacouncil")

def setup_logger(verbose: bool = False) -> None:
    """
    Configure the console logging behavior.
    Use verbose=True to show DEBUG logs.
    """
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Avoid duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        # Use a clean formatter that prints just the message, mimicking print statements
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

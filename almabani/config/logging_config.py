"""
Centralized logging configuration.
Sets up consistent logging across all modules.
"""
import logging
import os
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[Path] = None,
    log_format: Optional[str] = None,
    include_timestamp: bool = True
) -> logging.Logger:
    """
    Configure logging for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                   If None, reads from LOG_LEVEL env var, defaults to INFO
        log_file: Optional path to log file
                  If None, reads from LOG_FILE env var
        log_format: Custom log format string
        include_timestamp: Include timestamp in log filenames
    
    Returns:
        Configured root logger
    """
    # Read from environment variables if not provided
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO")
    
    if log_file is None:
        env_log_file = os.getenv("LOG_FILE")
        if env_log_file:
            log_file = Path(env_log_file)
    
    # Default format
    if log_format is None:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(log_format)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_file = Path(log_file)
        
        # If a directory is provided, create a file name inside it
        if log_file.is_dir() or log_file.suffix == '':
            target_dir = log_file
            filename = f"app.log"
        else:
            target_dir = log_file.parent
            filename = log_file.name
        
        # Add timestamp to filename if requested
        if include_timestamp:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = Path(filename).stem
            suffix = Path(filename).suffix or ".log"
            filename = f"{stem}_{timestamp}{suffix}"
        
        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / filename
        
        file_handler = logging.FileHandler(final_path, encoding='utf-8')
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        root_logger.info(f"Logging to file: {final_path}")
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def setup_module_logger(
    module_name: str,
    log_dir: Optional[Path] = None,
    log_level: str = "INFO"
) -> logging.Logger:
    """
    Set up logging for a specific module with optional file output.
    
    Args:
        module_name: Name of the module (e.g., 'parser', 'matcher')
        log_dir: Directory for log files (if None, console only)
        log_level: Logging level
    
    Returns:
        Configured logger
    """
    log_file = None
    if log_dir:
        log_dir = Path(log_dir)
        log_file = log_dir / f"{module_name}.log"
    
    setup_logging(
        log_level=log_level,
        log_file=log_file,
        include_timestamp=True
    )
    
    return logging.getLogger(module_name)

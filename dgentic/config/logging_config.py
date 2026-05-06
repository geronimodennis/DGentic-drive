"""Logging configuration for DGentic."""
import sys
import json
from loguru import logger
from config.settings import Settings, get_settings


def configure_logging(settings: Settings = None) -> None:
    """Configure logging for the application."""
    if settings is None:
        settings = get_settings()
    
    # Remove default handler
    logger.remove()
    
    # Create directory if it doesn't exist
    import os
    os.makedirs(settings.logs_directory, exist_ok=True)
    
    # Log format
    if settings.log_format == "json":
        log_format = "{message}"
    else:
        log_format = (
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )
    
    # Console handler
    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.log_level,
        colorize=True,
    )
    
    # File handler
    log_file = f"{settings.logs_directory}/dgentic.log"
    logger.add(
        log_file,
        format=log_format,
        level=settings.log_level,
        rotation="100 MB",
        retention="7 days",
    )
    
    # Error file handler
    error_file = f"{settings.logs_directory}/error.log"
    logger.add(
        error_file,
        format=log_format,
        level="ERROR",
        rotation="100 MB",
        retention="30 days",
    )


# Configure logging on import
configure_logging()

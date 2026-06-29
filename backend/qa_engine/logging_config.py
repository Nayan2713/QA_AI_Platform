import logging
import logging.handlers
import os

def configure_logging():
    """Configure logging for the application"""
    
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # File handler - all logs
    file_handler = logging.handlers.RotatingFileHandler(
        'logs/debug.log',
        maxBytes=0,  # Disable rotation on Windows to prevent WinError 32 PermissionError
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    
    # File handler - errors only
    error_handler = logging.handlers.RotatingFileHandler(
        'logs/error.log',
        maxBytes=0,  # Disable rotation on Windows to prevent WinError 32 PermissionError
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Formatter
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(levelname)s - %(name)s - %(message)s'
    )
    
    file_handler.setFormatter(detailed_formatter)
    error_handler.setFormatter(detailed_formatter)
    console_handler.setFormatter(simple_formatter)
    
    # Add handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)
    
    # Set specific logger levels
    logging.getLogger('django.db.backends').setLevel(logging.WARNING)
    logging.getLogger('celery').setLevel(logging.INFO)

# Call this in settings.py or manage.py
configure_logging()
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SyslogWriter:
    """Write syslog messages to severity-based log files"""
    
    def __init__(self, log_dir: str = 'logs') -> None:
        self.log_dir: Path = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.file_handles: Dict[str, Any] = {}
        self.lock: threading.Lock = threading.Lock()
        
        # Create log files for each severity
        self.severity_files: Dict[str, str] = {
            'emergency': 'emergency.log',
            'alert': 'alert.log',
            'critical': 'critical.log',
            'error': 'error.log',
            'warning': 'warning.log',
            'notice': 'notice.log',
            'info': 'info.log',
            'debug': 'debug.log'
        }
    
    def write(self, parsed_message: Dict[str, Any]) -> None:
        """Write parsed syslog message to appropriate log file"""
        severity = parsed_message.get('severity', 'info')
        filename = self.severity_files.get(severity, 'unknown.log')
        filepath = self.log_dir / filename
        
        with self.lock:
            try:
                with open(filepath, 'a') as f:
                    json.dump(parsed_message, f)
                    f.write('\n')
                logger.debug(f"Wrote message to {filename}")
            except Exception as e:
                logger.error(f"Error writing to {filename}: {e}")
    
    def close(self) -> None:
        """Close all open file handles"""
        with self.lock:
            for handle in self.file_handles.values():
                try:
                    handle.close()
                except Exception as e:
                    logger.error(f"Error closing file handle: {e}")



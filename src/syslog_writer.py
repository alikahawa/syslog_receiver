import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional, TextIO

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SyslogWriter:
    """Write syslog messages to severity-based log files with automatic rotation"""
    
    # Class-level constants (shared across all instances)
    SEVERITY_FILES: Dict[str, str] = {
        'emergency': 'emergency.log',
        'alert': 'alert.log',
        'critical': 'critical.log',
        'error': 'error.log',
        'warning': 'warning.log',
        'notice': 'notice.log',
        'info': 'info.log',
        'debug': 'debug.log'
    }
    
    def __init__(self, 
                 log_dir: str = 'logs',
                 max_bytes: int = 10 * 1024 * 1024,  # 10MB
                 backup_count: int = 5) -> None:
        """
        Initialize the syslog writer.
        
        Args:
            log_dir: Directory to store log files
            max_bytes: Maximum size per log file before rotation
            backup_count: Number of backup files to keep
        """
        self.log_dir: Path = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        self.max_bytes: int = max_bytes
        self.backup_count: int = backup_count
        
        # File handles cache (one per severity)
        self.file_handles: Dict[str, TextIO] = {}
        
        # Lock per severity for fine-grained concurrency
        self.locks: Dict[str, threading.Lock] = {}
        
        # Master lock for shutdown operations
        self.master_lock: threading.Lock = threading.Lock()
        
        # Flag to prevent writes after close
        self.is_closed: bool = False
    
    def _get_lock(self, severity: str) -> threading.Lock:
        """Get or create lock for specific severity level"""
        if severity not in self.locks:
            self.locks[severity] = threading.Lock()
        return self.locks[severity]
    
    def _get_file_handle(self, severity: str) -> Optional[TextIO]:
        """
        Get or create cached file handle for severity level.
        Returns None if writer is closed.
        """
        if self.is_closed:
            return None
        
        if severity not in self.file_handles:
            filename = self.SEVERITY_FILES.get(severity, 'unknown.log')
            filepath = self.log_dir / filename
            self.file_handles[severity] = open(filepath, 'a', buffering=8192)
        
        return self.file_handles[severity]
    
    def _rotate_file(self, severity: str) -> None:
        """
        Rotate log file when it exceeds max_bytes.
        Renames: app.log → app.log.1 → app.log.2 → ... → app.log.N
        """
        filename = self.SEVERITY_FILES.get(severity, 'unknown.log')
        filepath = self.log_dir / filename
        
        # Close current handle
        if severity in self.file_handles:
            self.file_handles[severity].close()
            del self.file_handles[severity]
        
        # Rotate existing backups (N-1 → N, ... , 1 → 2)
        for i in range(self.backup_count - 1, 0, -1):
            old_backup = self.log_dir / f"{filename}.{i}"
            new_backup = self.log_dir / f"{filename}.{i + 1}"
            
            if old_backup.exists():
                if new_backup.exists():
                    new_backup.unlink()  # Remove oldest
                old_backup.rename(new_backup)
        
        # Rotate current file to .1
        if filepath.exists():
            backup = self.log_dir / f"{filename}.1"
            filepath.rename(backup)
        
        logger.info(f"Rotated {filename} (kept {self.backup_count} backups)")
    
    def _should_rotate(self, severity: str) -> bool:
        """Check if file should be rotated based on size"""
        filename = self.SEVERITY_FILES.get(severity, 'unknown.log')
        filepath = self.log_dir / filename
        
        return filepath.exists() and filepath.stat().st_size >= self.max_bytes
    
    def write(self, parsed_message: Dict[str, Any]) -> None:
        """
        Write parsed syslog message to appropriate severity-based log file.
        Thread-safe with per-severity locking.
        """
        # Quick check without lock
        if self.is_closed:
            logger.warning("Attempted write to closed SyslogWriter")
            return
        
        severity = parsed_message.get('severity', 'info')
        
        # Validate severity (prevent path traversal)
        if severity not in self.SEVERITY_FILES:
            severity = 'unknown'
        
        lock = self._get_lock(severity)
        
        with lock:
            # Double-check after acquiring lock
            if self.is_closed:
                return
            
            try:
                # Rotate if needed
                if self._should_rotate(severity):
                    self._rotate_file(severity)
                
                # Get file handle (creates if needed)
                file_handle = self._get_file_handle(severity)
                if file_handle is None:
                    return  # Writer is closed
                
                # Write JSON message
                json.dump(parsed_message, file_handle)
                file_handle.write('\n')
                file_handle.flush()  # Ensure data reaches disk
                
                logger.debug(f"Wrote message to {severity}.log")
                
            except IOError as e:
                logger.error(f"I/O error writing to {severity}.log: {e}")
            except Exception as e:
                logger.error(f"Unexpected error writing message: {e}", exc_info=True)
    
    def flush_all(self) -> None:
        """Flush all open file handles to disk"""
        for severity, lock in self.locks.items():
            with lock:
                if severity in self.file_handles:
                    try:
                        self.file_handles[severity].flush()
                    except Exception as e:
                        logger.error(f"Error flushing {severity}.log: {e}")
    
    def close(self) -> None:
        """
        Close all open file handles safely.
        Acquires all locks to ensure no concurrent writes.
        """
        with self.master_lock:
            if self.is_closed:
                logger.debug("SyslogWriter already closed")
                return
            
            # Set flag to prevent new writes
            self.is_closed = True
            
            # Acquire all per-severity locks (prevents concurrent writes)
            acquired_locks = []
            for severity in list(self.locks.keys()):
                lock = self.locks[severity]
                lock.acquire()
                acquired_locks.append(lock)
            
            try:
                # Close all file handles
                for severity, file_handle in list(self.file_handles.items()):
                    try:
                        file_handle.flush()
                        file_handle.close()
                        logger.info(f"Closed {severity}.log")
                    except Exception as e:
                        logger.error(f"Error closing {severity}.log: {e}")
                
                # Clear collections
                self.file_handles.clear()
                
            finally:
                # Always release locks (even if close failed)
                for lock in acquired_locks:
                    try:
                        lock.release()
                    except RuntimeError:
                        pass  # Already released
    
    def __enter__(self) -> 'SyslogWriter':
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """Context manager exit - closes all resources"""
        self.close()
        return False  # Don't suppress exceptions


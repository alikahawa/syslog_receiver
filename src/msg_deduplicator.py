import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MessageDeduplicator:
    """Handle message deduplication based on source IP, priority, and message content"""
    
    def __init__(self, window_minutes: int = 10) -> None:
        self.window_minutes: int = window_minutes
        self.seen_messages: Dict[Tuple[str, int, str], datetime] = {}
        self.lock: threading.Lock = threading.Lock()
        
        # Start cleanup thread
        self.cleanup_thread: threading.Thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
    
    def should_write(self, source_ip: str, priority: int, message: str) -> bool:
        """
        Check if message should be written to file.
        Returns True if this is a new message or outside the deduplication window.
        """
        key: Tuple[str, int, str] = (source_ip, priority, message)
        current_time: datetime = datetime.now()
        
        with self.lock:
            if key in self.seen_messages:
                last_seen = self.seen_messages[key]
                if current_time - last_seen < timedelta(minutes=self.window_minutes):
                    logger.debug(f"Duplicate message suppressed from {source_ip}")
                    return False
            
            self.seen_messages[key] = current_time
            return True

    def _cleanup_loop(self) -> None:
        """Periodically clean up old entries from seen_messages"""
        while True:
            time.sleep(60)  # Check every minute
            self._cleanup()
    
    def _cleanup(self) -> None:
        """Remove entries older than the deduplication window"""
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(minutes=self.window_minutes)
        
        with self.lock:
            keys_to_remove = [
                key for key, timestamp in self.seen_messages.items()
                if timestamp < cutoff_time
            ]
            for key in keys_to_remove:
                del self.seen_messages[key]
            
            if keys_to_remove:
                logger.debug(f"Cleaned up {len(keys_to_remove)} old deduplication entries")

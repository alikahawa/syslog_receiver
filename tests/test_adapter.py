"""
Test Adapter Module
Provides compatibility layer for tests to work with actual implementation
"""
from src.msg_deduplicator import MessageDeduplicator as ActualDeduplicator


class MessageDeduplicatorTestAdapter:
    """Adapter to make MessageDeduplicator work with test expectations"""
    
    def __init__(self, window_minutes: int = 10):
        self._dedup = ActualDeduplicator(window_minutes=window_minutes)
        self.message_hashes = {}  # For tracking in tests
        
    def is_duplicate(self, message: str) -> bool:
        """
        Adapter method: Maps test's is_duplicate() to actual should_write()
        Returns True if duplicate, False if unique (opposite of should_write)
        """
        # Use dummy source_ip and priority for tests
        source_ip = "127.0.0.1"
        priority = 14
        
        # should_write returns True for new messages, False for duplicates
        # is_duplicate should return False for new messages, True for duplicates
        should_write = self._dedup.should_write(source_ip, priority, message)
        
        # Track for test statistics
        if not should_write:  # It's a duplicate
            pass  # Already tracked
        else:  # New message
            key = (source_ip, priority, message)
            self.message_hashes[message] = key
            
        return not should_write  # Invert: duplicate=True, new=False

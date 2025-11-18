"""Unit tests for MessageDeduplicator"""

import time
from datetime import datetime, timedelta

import pytest

from src.msg_deduplicator import MessageDeduplicator


class TestMessageDeduplicator:
    """Tests for message deduplication logic"""
    
    def test_first_message_is_not_duplicate(self):
        """Test that first occurrence of message should be written"""
        dedup = MessageDeduplicator(window_minutes=10)
        
        message = "Test message 1"
        # First occurrence should write (returns True)
        assert dedup.should_write("192.168.1.1", 14, message) is True
    
    def test_immediate_duplicate_is_detected(self):
        """Test that immediate duplicate is suppressed"""
        dedup = MessageDeduplicator(window_minutes=10)
        
        message = "Test message 1"
        source_ip = "192.168.1.1"
        priority = 14
        
        # First occurrence should write
        assert dedup.should_write(source_ip, priority, message) is True
        # Duplicate should not write
        assert dedup.should_write(source_ip, priority, message) is False
    
    def test_different_messages_not_duplicates(self):
        """Test that different messages are all written"""
        dedup = MessageDeduplicator(window_minutes=10)
        source_ip = "192.168.1.1"
        priority = 14
        
        assert dedup.should_write(source_ip, priority, "Message A") is True
        assert dedup.should_write(source_ip, priority, "Message B") is True
        assert dedup.should_write(source_ip, priority, "Message C") is True
    
    def test_duplicate_detection_across_multiple_calls(self):
        """Test duplicate detection across multiple identical messages"""
        dedup = MessageDeduplicator(window_minutes=10)
        
        message = "Repeated message"
        source_ip = "192.168.1.1"
        priority = 14
        
        # First is unique (should write)
        assert dedup.should_write(source_ip, priority, message) is True
        
        # Next 5 are duplicates (should not write)
        for _ in range(5):
            assert dedup.should_write(source_ip, priority, message) is False
    
    def test_deduplication_window_expiry(self):
        """Test that messages outside window can be written again"""
        # Use very short window for testing
        dedup = MessageDeduplicator(window_minutes=0.01)  # ~0.6 seconds
        
        message = "Expiring message"
        source_ip = "192.168.1.1"
        priority = 14
        
        # First occurrence should write
        assert dedup.should_write(source_ip, priority, message) is True
        
        # Should be suppressed immediately (duplicate)
        assert dedup.should_write(source_ip, priority, message) is False
        
        # Wait for window to expire
        time.sleep(1)
        
        # Should write again after window expires
        assert dedup.should_write(source_ip, priority, message) is True
    
    def test_cleanup_removes_old_entries(self):
        """Test that cleanup removes expired entries"""
        dedup = MessageDeduplicator(window_minutes=0.01)
        source_ip = "192.168.1.1"
        priority = 14
        
        # Add several messages
        for i in range(10):
            dedup.should_write(source_ip, priority, f"Message {i}")
        
        # Verify messages are stored
        assert len(dedup.seen_messages) == 10
        
        # Wait for expiry
        time.sleep(1)
        
        # Manually trigger cleanup
        dedup._cleanup()
        
        # Old messages should be cleaned up
        assert len(dedup.seen_messages) == 0
    
    def test_case_sensitive_deduplication(self):
        """Test that deduplication is case-sensitive"""
        dedup = MessageDeduplicator(window_minutes=10)
        source_ip = "192.168.1.1"
        priority = 14
        
        # Different cases are different messages
        assert dedup.should_write(source_ip, priority, "Test Message") is True
        assert dedup.should_write(source_ip, priority, "test message") is True
        assert dedup.should_write(source_ip, priority, "TEST MESSAGE") is True
        
        # But exact match is duplicate
        assert dedup.should_write(source_ip, priority, "Test Message") is False
    
    def test_whitespace_differences(self):
        """Test that whitespace differences create different messages"""
        dedup = MessageDeduplicator(window_minutes=10)
        source_ip = "192.168.1.1"
        priority = 14
        
        # All different due to whitespace
        assert dedup.should_write(source_ip, priority, "Test message") is True
        assert dedup.should_write(source_ip, priority, "Test  message") is True  # Extra space
        assert dedup.should_write(source_ip, priority, "Test message ") is True  # Trailing space
        assert dedup.should_write(source_ip, priority, " Test message") is True  # Leading space
    
    def test_unicode_message_deduplication(self):
        """Test deduplication with Unicode content"""
        dedup = MessageDeduplicator(window_minutes=10)
        source_ip = "192.168.1.1"
        priority = 14
        
        message = "Unicode test: 你好世界 🚀"
        
        assert dedup.should_write(source_ip, priority, message) is True
        assert dedup.should_write(source_ip, priority, message) is False
    
    def test_large_message_deduplication(self):
        """Test deduplication with large messages"""
        dedup = MessageDeduplicator(window_minutes=10)
        source_ip = "192.168.1.1"
        priority = 14
        
        large_message = "A" * 10000  # 10KB message
        
        assert dedup.should_write(source_ip, priority, large_message) is True
        assert dedup.should_write(source_ip, priority, large_message) is False
    
    def test_concurrent_different_messages(self):
        """Test handling many different messages concurrently"""
        dedup = MessageDeduplicator(window_minutes=10)
        source_ip = "192.168.1.1"
        priority = 14
        
        # Add 1000 unique messages - all should write
        for i in range(1000):
            assert dedup.should_write(source_ip, priority, f"Unique message {i}") is True
        
        # Verify all are stored
        assert len(dedup.seen_messages) == 1000
        
        # Re-checking first message should be duplicate (not write)
        assert dedup.should_write(source_ip, priority, "Unique message 0") is False
    
    def test_empty_message_handling(self):
        """Test handling of empty messages"""
        dedup = MessageDeduplicator(window_minutes=10)
        source_ip = "192.168.1.1"
        priority = 14
        
        # Empty strings are valid but distinct from non-empty
        assert dedup.should_write(source_ip, priority, "") is True
        assert dedup.should_write(source_ip, priority, "") is False  # Duplicate
        assert dedup.should_write(source_ip, priority, "Non-empty") is True
    
    def test_thread_safety_simulation(self):
        """Test that deduplicator handles concurrent access (basic simulation)"""
        import threading
        
        dedup = MessageDeduplicator(window_minutes=10)
        results = []
        source_ip = "192.168.1.1"
        priority = 14
        
        def check_message(msg: str, iterations: int):
            for _ in range(iterations):
                result = dedup.should_write(source_ip, priority, msg)
                results.append(result)
                time.sleep(0.001)
        
        # Create threads checking same message
        threads = [
            threading.Thread(target=check_message, args=("Concurrent test", 10))
            for _ in range(5)
        ]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # At least one thread should see it as new (should_write=True)
        assert results.count(True) >= 1  # At least one wrote it
        assert results.count(False) >= 40  # Most saw it as duplicate
    
    def test_deduplication_statistics(self):
        """Test tracking of deduplication statistics"""
        dedup = MessageDeduplicator(window_minutes=10)
        source_ip = "192.168.1.1"
        priority = 14
        
        # Send same message 10 times
        message = "Repeated message"
        for _ in range(10):
            dedup.should_write(source_ip, priority, message)
        
        # Send 5 unique messages
        for i in range(5):
            dedup.should_write(source_ip, priority, f"Unique {i}")
        
        # Should have 6 unique keys stored (1 repeated + 5 unique)
        assert len(dedup.seen_messages) == 6

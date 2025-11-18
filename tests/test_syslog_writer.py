"""Unit tests for SyslogWriter"""

import json
import os
from pathlib import Path

import pytest

from src.syslog_writer import SyslogWriter


class TestSyslogWriter:
    """Tests for severity-based log file writing"""
    
    def test_writer_creates_log_directory(self, temp_log_dir):
        """Test that writer creates log directory if it doesn't exist"""
        new_dir = os.path.join(temp_log_dir, 'new_logs')
        writer = SyslogWriter(log_dir=new_dir)
        
        assert os.path.exists(new_dir)
        writer.close()
    
    def test_write_to_each_severity_level(self, syslog_writer, temp_log_dir):
        """Test writing messages to all severity levels"""
        severities = ['emergency', 'alert', 'critical', 'error', 
                      'warning', 'notice', 'info', 'debug']
        
        for severity in severities:
            parsed_msg = {
                'severity': severity,
                'facility': 'user',
                'priority': 14,
                'timestamp': '2025-11-17T10:30:45',
                'hostname': 'test-host',
                'app_name': 'test-app',
                'message': f'Test message for {severity}'
            }
            syslog_writer.write(parsed_msg)
        
        syslog_writer.flush_all()
        
        # Verify each severity file was created
        for severity in severities:
            log_file = os.path.join(temp_log_dir, f'{severity}.log')
            assert os.path.exists(log_file), f"Missing {severity}.log"
            
            # Verify JSON format
            with open(log_file, 'r') as f:
                line = f.readline()
                data = json.loads(line)
                assert data['severity'] == severity
                assert f'Test message for {severity}' in data['message']
    
    def test_write_multiple_messages_same_severity(self, syslog_writer, temp_log_dir):
        """Test writing multiple messages to same severity file"""
        for i in range(10):
            parsed_msg = {
                'severity': 'info',
                'facility': 'user',
                'priority': 14,
                'timestamp': '2025-11-17T10:30:45',
                'hostname': 'test-host',
                'app_name': 'test-app',
                'message': f'Info message {i}'
            }
            syslog_writer.write(parsed_msg)
        
        syslog_writer.flush_all()
        
        # Verify all messages written
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 10
            
            # Verify each message is valid JSON
            for i, line in enumerate(lines):
                data = json.loads(line)
                assert f'Info message {i}' in data['message']
    
    def test_json_format_correctness(self, syslog_writer, temp_log_dir):
        """Test that written data is valid JSON with correct fields"""
        parsed_msg = {
            'severity': 'warning',
            'facility': 'daemon',
            'priority': 28,
            'timestamp': '2025-11-17T10:30:45.123Z',
            'hostname': 'web01',
            'app_name': 'nginx',
            'message': 'Slow query detected'
        }
        syslog_writer.write(parsed_msg)
        syslog_writer.flush_all()
        
        log_file = os.path.join(temp_log_dir, 'warning.log')
        with open(log_file, 'r') as f:
            data = json.loads(f.readline())
            
            # Verify all fields present
            assert data['severity'] == 'warning'
            assert data['facility'] == 'daemon'
            assert data['priority'] == 28
            assert data['timestamp'] == '2025-11-17T10:30:45.123Z'
            assert data['hostname'] == 'web01'
            assert data['app_name'] == 'nginx'
            assert data['message'] == 'Slow query detected'
    
    def test_unicode_content_handling(self, syslog_writer, temp_log_dir):
        """Test writing messages with Unicode characters"""
        parsed_msg = {
            'severity': 'info',
            'facility': 'user',
            'priority': 14,
            'timestamp': '2025-11-17T10:30:45',
            'hostname': 'server1',
            'app_name': 'app',
            'message': 'Unicode test: 你好世界 🚀 émoji'
        }
        syslog_writer.write(parsed_msg)
        syslog_writer.flush_all()
        
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r', encoding='utf-8') as f:
            data = json.loads(f.readline())
            assert '你好世界' in data['message']
            assert '🚀' in data['message']
            assert 'émoji' in data['message']
    
    def test_large_message_handling(self, syslog_writer, temp_log_dir):
        """Test writing very large messages"""
        large_content = 'A' * 50000  # 50KB
        parsed_msg = {
            'severity': 'debug',
            'facility': 'user',
            'priority': 15,
            'timestamp': '2025-11-17T10:30:45',
            'hostname': 'server1',
            'app_name': 'app',
            'message': large_content
        }
        syslog_writer.write(parsed_msg)
        syslog_writer.flush_all()
        
        log_file = os.path.join(temp_log_dir, 'debug.log')
        with open(log_file, 'r') as f:
            data = json.loads(f.readline())
            assert len(data['message']) == 50000
            assert data['message'] == large_content
    
    def test_flush_all_writes_to_disk(self, syslog_writer, temp_log_dir):
        """Test that flush_all ensures data is written to disk"""
        for i in range(5):
            parsed_msg = {
                'severity': 'info',
                'facility': 'user',
                'priority': 14,
                'timestamp': '2025-11-17T10:30:45',
                'hostname': 'server1',
                'app_name': 'app',
                'message': f'Message {i}'
            }
            syslog_writer.write(parsed_msg)
        
        # Don't close writer yet
        syslog_writer.flush_all()
        
        # Data should be readable immediately after flush
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 5
    
    def test_writer_close_flushes_data(self, temp_log_dir):
        """Test that closing writer flushes all pending data"""
        writer = SyslogWriter(log_dir=temp_log_dir)
        
        parsed_msg = {
            'severity': 'error',
            'facility': 'user',
            'priority': 11,
            'timestamp': '2025-11-17T10:30:45',
            'hostname': 'server1',
            'app_name': 'app',
            'message': 'Error occurred'
        }
        writer.write(parsed_msg)
        writer.close()
        
        # Data should be written after close
        log_file = os.path.join(temp_log_dir, 'error.log')
        with open(log_file, 'r') as f:
            data = json.loads(f.readline())
            assert data['message'] == 'Error occurred'
    
    def test_thread_safety_multiple_writes(self, syslog_writer, temp_log_dir):
        """Test concurrent writes from multiple threads"""
        import threading
        
        def write_messages(severity: str, count: int):
            for i in range(count):
                parsed_msg = {
                    'severity': severity,
                    'facility': 'user',
                    'priority': 14,
                    'timestamp': '2025-11-17T10:30:45',
                    'hostname': 'server1',
                    'app_name': 'app',
                    'message': f'{severity} message {i}'
                }
                syslog_writer.write(parsed_msg)
        
        # Create threads writing to different severities
        threads = [
            threading.Thread(target=write_messages, args=('info', 50)),
            threading.Thread(target=write_messages, args=('warning', 50)),
            threading.Thread(target=write_messages, args=('error', 50)),
        ]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        syslog_writer.flush_all()
        
        # Verify all messages written correctly
        for severity in ['info', 'warning', 'error']:
            log_file = os.path.join(temp_log_dir, f'{severity}.log')
            with open(log_file, 'r') as f:
                lines = f.readlines()
                assert len(lines) == 50, f"Expected 50 lines in {severity}.log, got {len(lines)}"
    
    def test_invalid_severity_handling(self, syslog_writer):
        """Test handling of invalid severity level"""
        parsed_msg = {
            'severity': 'invalid_severity',
            'facility': 'user',
            'priority': 14,
            'timestamp': '2025-11-17T10:30:45',
            'hostname': 'server1',
            'app_name': 'app',
            'message': 'Test message'
        }
        
        # Should handle gracefully without crashing
        try:
            syslog_writer.write(parsed_msg)
            syslog_writer.flush_all()
        except Exception as e:
            pytest.fail(f"Writer should handle invalid severity gracefully: {e}")
    
    def test_file_rotation_behavior(self, temp_log_dir):
        """Test that file rotation works when size limit is reached"""
        # Create writer with small max file size for testing
        writer = SyslogWriter(log_dir=temp_log_dir, max_bytes=1024)  # 1KB
        
        # Write enough data to trigger rotation
        for i in range(100):
            parsed_msg = {
                'severity': 'info',
                'facility': 'user',
                'priority': 14,
                'timestamp': '2025-11-17T10:30:45',
                'hostname': 'server1',
                'app_name': 'app',
                'message': f'Test message {i}' + 'A' * 200  # Make each message ~200 bytes
            }
            writer.write(parsed_msg)
        
        writer.close()
        
        # Check if rotation files exist (info.log.1, info.log.2, etc.)
        log_files = list(Path(temp_log_dir).glob('info.log*'))
        assert len(log_files) > 1, "File rotation should have created backup files"
    
    def test_context_manager_usage(self, temp_log_dir):
        """Test that writer works as context manager"""
        with SyslogWriter(log_dir=temp_log_dir) as writer:
            parsed_msg = {
                'severity': 'info',
                'facility': 'user',
                'priority': 14,
                'timestamp': '2025-11-17T10:30:45',
                'hostname': 'server1',
                'app_name': 'app',
                'message': 'Context manager test'
            }
            writer.write(parsed_msg)
        
        # Data should be written after context exits
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            data = json.loads(f.readline())
            assert data['message'] == 'Context manager test'

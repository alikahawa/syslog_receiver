"""Unit tests for SyslogParser"""

from datetime import datetime

import pytest

from src.syslog_parser import SyslogParser


class TestSyslogParserRFC3164:
    """Tests for RFC 3164 (BSD syslog) format parsing"""
    
    def test_parse_valid_rfc3164_message(self):
        """Test parsing a valid RFC 3164 message"""
        message = '<14>Jan 15 10:30:45 server1 app[1234]: User login successful'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert result['severity'] == 'info'
        assert result['facility'] == 'user'
        assert result['priority'] == 14
        assert result['hostname'] == 'server1'
        # RFC3164 doesn't parse app_name separately - it's in the message
        assert 'app[1234]: User login successful' in result['message']
    
    def test_parse_all_severity_levels(self):
        """Test parsing messages with all 8 severity levels"""
        severities = [
            (0, 'emergency'), (1, 'alert'), (2, 'critical'), (3, 'error'),
            (4, 'warning'), (5, 'notice'), (6, 'info'), (7, 'debug')
        ]
        
        for sev_num, sev_name in severities:
            priority = 8 + sev_num  # user facility (1) << 3
            message = f'<{priority}>Jan 15 10:30:45 server1 test: Severity {sev_num}'
            result = SyslogParser.parse(message)
            
            assert result is not None
            assert result['severity'] == sev_name, f"Failed for severity {sev_num}"
            assert result['priority'] == priority
    
    def test_parse_various_facilities(self):
        """Test parsing messages from different facilities"""
        facilities = [
            (0, 'kern'),     # kernel messages
            (1, 'user'),     # user-level messages
            (3, 'daemon'),   # system daemons
            (4, 'auth'),     # security/authentication
            (16, 'local0'),  # local use 0
            (23, 'local7'),  # local use 7
        ]
        
        for fac_num, fac_name in facilities:
            priority = (fac_num << 3) + 3  # error severity
            message = f'<{priority}>Jan 15 10:30:45 server1 test: Facility {fac_name}'
            result = SyslogParser.parse(message)
            
            assert result is not None
            assert result['facility'] == fac_name, f"Failed for facility {fac_name}"
    
    def test_parse_message_with_process_id(self):
        """Test parsing message with process ID in brackets"""
        message = '<14>Jan 15 10:30:45 web01 nginx[5678]: Connection from 192.168.1.100'
        result = SyslogParser.parse(message)
        
        assert result is not None
        # RFC3164 includes app[pid] in message field
        assert 'nginx[5678]' in result['message']
        assert 'Connection from 192.168.1.100' in result['message']
    
    def test_parse_message_without_hostname(self):
        """Test parsing message missing hostname"""
        message = '<14>Jan 15 10:30:45 app: Message without hostname'
        result = SyslogParser.parse(message)
        
        # Parser should still extract what it can
        assert result is not None
        assert result['severity'] == 'info'
    
    def test_parse_long_message(self):
        """Test parsing very long message content"""
        long_content = 'A' * 5000
        message = f'<14>Jan 15 10:30:45 server1 app: {long_content}'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert long_content in result['message']
        # Message includes 'app: ' prefix from RFC3164 format
        assert len(result['message']) >= len(long_content)
    
    def test_parse_unicode_content(self):
        """Test parsing message with Unicode characters"""
        message = '<14>Jan 15 10:30:45 server1 app: Unicode test 你好世界 🚀'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert '你好世界' in result['message']
        assert '🚀' in result['message']


class TestSyslogParserRFC5424:
    """Tests for RFC 5424 (structured syslog) format parsing"""
    
    def test_parse_valid_rfc5424_message(self):
        """Test parsing a valid RFC 5424 message"""
        message = '<14>1 2025-11-17T10:30:45.123Z server1 app 1234 MSG001 - Application started'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert result['severity'] == 'info'
        assert result['hostname'] == 'server1'
        assert result['app_name'] == 'app'
        assert 'Application started' in result['message']
    
    def test_parse_rfc5424_with_structured_data(self):
        """Test parsing RFC 5424 message with structured data"""
        message = '<14>1 2025-11-17T10:30:45.123Z web01 nginx 5678 REQ [request@12345 method="GET" path="/api" status="200"] Request OK'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert result['severity'] == 'info'
        assert result['hostname'] == 'web01'
        # Structured data should be in message
        assert 'request@12345' in result['message'] or 'method' in result['message']
    
    def test_parse_rfc5424_nil_values(self):
        """Test parsing RFC 5424 with nil (- character) values"""
        message = '<14>1 2025-11-17T10:30:45.123Z - - - - - Minimal message'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert result['severity'] == 'info'


class TestSyslogParserEdgeCases:
    """Tests for edge cases and malformed messages"""
    
    def test_parse_malformed_no_priority(self):
        """Test parsing message without priority tag"""
        message = 'Jan 15 10:30:45 server1 app: No priority tag'
        result = SyslogParser.parse(message)
        
        # Parser should handle gracefully (may return None or default values)
        if result:
            assert 'message' in result
    
    def test_parse_malformed_empty_priority(self):
        """Test parsing message with empty priority brackets"""
        message = '<>Jan 15 10:30:45 server1 app: Empty priority'
        result = SyslogParser.parse(message)
        
        # Should handle gracefully
        assert result is None or 'message' in result
    
    def test_parse_malformed_invalid_priority(self):
        """Test parsing message with invalid priority value"""
        message = '<999>Jan 15 10:30:45 server1 app: Invalid priority'
        result = SyslogParser.parse(message)
        
        # Priority 999 is out of valid range (0-191)
        # Parser should handle gracefully
        assert result is None or 'message' in result
    
    def test_parse_empty_message(self):
        """Test parsing empty string"""
        result = SyslogParser.parse('')
        # Parser returns a dict with defaults even for empty input
        assert result is not None
        assert 'message' in result
    
    def test_parse_whitespace_only(self):
        """Test parsing whitespace-only message"""
        result = SyslogParser.parse('   \n\t  ')
        # Parser returns a dict with defaults even for whitespace
        assert result is not None
        assert 'message' in result
    
    def test_parse_only_priority(self):
        """Test parsing message with only priority tag"""
        result = SyslogParser.parse('<14>')
        # Should handle gracefully
        assert result is None or 'severity' in result
    
    def test_parse_binary_data(self):
        """Test parsing message with binary data"""
        message = '<14>Jan 15 10:30:45 server1 app: Binary data: \x00\x01\x02\xff'
        result = SyslogParser.parse(message)
        
        # Should handle gracefully without crashing
        assert result is None or isinstance(result, dict)


class TestSyslogParserRealWorld:
    """Tests using real-world log message examples"""
    
    def test_parse_nginx_access_log(self):
        """Test parsing typical nginx access log"""
        message = '<14>Jan 15 10:30:45 web01 nginx: 192.168.1.100 - - [15/Jan/2025:10:30:45 +0000] "GET /api/v1/users HTTP/1.1" 200 1234'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert result['severity'] == 'info'
        assert result['hostname'] == 'web01'
        assert '192.168.1.100' in result['message']
    
    def test_parse_apache_error_log(self):
        """Test parsing Apache error log"""
        message = '<11>Jan 15 10:30:45 web02 apache2: [error] [client 192.168.1.100:54321] File does not exist'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert result['severity'] == 'error'
        assert 'apache2' in result['message']
    
    def test_parse_ssh_auth_log(self):
        """Test parsing SSH authentication log"""
        message = '<14>Jan 15 10:30:45 server1 sshd[12345]: Accepted publickey for admin from 192.168.1.50'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert result['severity'] == 'info'
        assert 'sshd' in result['message']
    
    def test_parse_kernel_message(self):
        """Test parsing kernel panic message"""
        message = '<8>Jan 15 10:30:45 server1 kernel: Out of memory: Kill process 12345'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert result['severity'] == 'emergency'
        assert 'kernel' in result['message']
    
    def test_parse_firewall_log(self):
        """Test parsing firewall block message"""
        message = '<12>Jan 15 10:30:45 fw01 kernel: [UFW BLOCK] IN=eth0 OUT= SRC=203.0.113.100 DST=192.168.1.10'
        result = SyslogParser.parse(message)
        
        assert result is not None
        assert result['severity'] == 'warning'
        assert 'UFW BLOCK' in result['message']

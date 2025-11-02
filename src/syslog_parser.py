import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Pattern

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SyslogParser:
    """
    Parse syslog messages according to RFC 5424 and RFC 3164
    https://devops.com/syslogs-in-linux-understanding-facilities-and-levels/
    """
    # Syslog severity levels
    SEVERITY_MAP: Dict[int, str] = {
        0: 'emergency',
        1: 'alert',
        2: 'critical',
        3: 'error',
        4: 'warning',
        5: 'notice',
        6: 'info',
        7: 'debug'
    }
    
    # Syslog facilities
    FACILITY_MAP: Dict[int, str] = {
        0: 'kern', 1: 'user', 2: 'mail', 3: 'daemon',
        4: 'auth', 5: 'syslog', 6: 'lpr', 7: 'news',
        8: 'uucp', 9: 'cron', 10: 'authpriv', 11: 'ftp',
        12: 'ntp', 13: 'security', 14: 'console', 15: 'solaris-cron',
        16: 'local0', 17: 'local1', 18: 'local2', 19: 'local3',
        20: 'local4', 21: 'local5', 22: 'local6', 23: 'local7'
    }

    """
    # RFC 5424 pattern
    RFC5424 is a standardized format for Syslog messages,
    including a header with fields for priority, version,
    timestamp, hostname, app-name, process ID, and message ID,
    followed by an optional structured data field and the message itself.
    """
    RFC5424_PATTERN: Pattern[str] = re.compile(
        r'^<(?P<pri>\d+)>(?P<ver>\d+)\s+'
        r'(?P<timestamp>\S+)\s+(?P<hostname>\S+)\s+(?P<app>\S+)\s+'
        r'(?P<procid>\S+)\s+(?P<msgid>\S+)\s+(?P<sd>\S+)\s*(?P<msg>.*)$'
    )
    
    """
    # RFC 3164 pattern
    The RFC 3164 format, also known as the BSD syslog format,
    is a traditional logging format with a header consisting of
    a priority value and a timestamp, followed by the hostname,
    a tag, and the message content.
    The timestamp is in the "Mmm dd hh:mm:ss" format,
    the tag typically indicates the program that generated the message,
    and the rest of the line is the message content.
    It's important to note that RFC 3164 is an informational,
    rather than a strict standard,
    and has been superseded by the more modern and structured RFC 5424
    
    """
    RFC3164_PATTERN: Pattern[str] = re.compile(
        r'^<(?P<pri>\d+)>(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+'
        r'(?P<hostname>\S+)\s+(?P<msg>.*)$'
    )

    @classmethod
    def parse(cls, message: str) -> Dict[str, Any]:
        """
        Parse a syslog message and return structured data
        try to match with RFC5424 or RFC3164
        If that does not work, treat the message as plain message
        and get as much information as possible
        """
        try:
            match = cls.RFC5424_PATTERN.match(message)
            if match:
                return cls._parse_rfc5424(match)
            
            match = cls.RFC3164_PATTERN.match(message)
            if match:
                return cls._parse_rfc3164(match)
            
            pri_match = re.match(r'^<(\d+)>(.*)$', message)
            if pri_match:
                pri = int(pri_match.group(1))
                return {
                    'priority': pri,
                    'facility': cls.FACILITY_MAP.get(pri >> 3, 'unknown'),
                    'severity': cls.SEVERITY_MAP.get(pri & 0x07, 'unknown'),
                    'message': pri_match.group(2),
                    'raw': message,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            
            return {
                'priority': 13,  # user.notice
                'facility': 'user',
                'severity': 'notice',
                'message': message,
                'raw': message,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error parsing syslog message: {e}")
            return {
                'priority': 13,
                'facility': 'user',
                'severity': 'error',
                'message': message,
                'raw': message,
                'parse_error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    @classmethod
    def _parse_rfc5424(cls, match: re.Match[str]) -> Dict[str, Any]:
        """Parse RFC 5424 format syslog message"""
        data = match.groupdict()
        pri = int(data['pri'])
        
        return {
            'priority': pri,
            'facility': cls.FACILITY_MAP.get(pri >> 3, 'unknown'),
            'severity': cls.SEVERITY_MAP.get(pri & 0x07, 'unknown'),
            'version': data['ver'],
            'timestamp': data['timestamp'],
            'hostname': data['hostname'],
            'app_name': data['app'],
            'proc_id': data['procid'],
            'msg_id': data['msgid'],
            'structured_data': data['sd'],
            'message': data['msg'],
            'raw': match.string,
            'format': 'RFC5424'
        }

    @classmethod
    def _parse_rfc3164(cls, match: re.Match[str]) -> Dict[str, Any]:
        """Parse RFC 3164 format syslog message"""
        data = match.groupdict()
        pri = int(data['pri'])
        
        return {
            'priority': pri,
            'facility': cls.FACILITY_MAP.get(pri >> 3, 'unknown'),
            'severity': cls.SEVERITY_MAP.get(pri & 0x07, 'unknown'),
            'timestamp': data['timestamp'],
            'hostname': data['hostname'],
            'message': data['msg'],
            'raw': match.string,
            'format': 'RFC3164'
        }


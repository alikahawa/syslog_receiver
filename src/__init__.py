"""
Syslog Receiver Application Package

A production-ready Python application for receiving, parsing, and storing 
syslog messages over UDP and TLS with automatic deduplication.
"""

from .msg_deduplicator import MessageDeduplicator
from .octet_counting_reader import OctetCountingReader
from .syslog_parser import SyslogParser
from .syslog_writer import SyslogWriter
from .tls_syslog_receiver import TLSSyslogReceiver
from .udp_syslog_receiver import UDPSyslogReceiver

__all__ = [
    'MessageDeduplicator',
    'OctetCountingReader',
    'SyslogParser',
    'SyslogWriter',
    'TLSSyslogReceiver',
    'UDPSyslogReceiver',
]

__version__ = '1.0.0'

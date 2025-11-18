"""Pytest configuration and shared fixtures for test suite"""

import os
import socket
import ssl
import tempfile
import threading
import time
from pathlib import Path
from typing import Generator, Tuple

import pytest

from src.msg_deduplicator import MessageDeduplicator
from src.syslog_writer import SyslogWriter
from src.tls_syslog_receiver import TLSSyslogReceiver
from src.udp_syslog_receiver import UDPSyslogReceiver
from tests.test_adapter import MessageDeduplicatorTestAdapter


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "unit: Unit tests for individual components")
    config.addinivalue_line("markers", "integration: Integration tests requiring network")
    config.addinivalue_line("markers", "scenario: Real-world scenario and performance tests")
    config.addinivalue_line("markers", "slow: Tests that take longer than 1 second")


@pytest.fixture
def temp_log_dir() -> Generator[str, None, None]:
    """Create temporary directory for log files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def syslog_writer(temp_log_dir: str) -> Generator[SyslogWriter, None, None]:
    """Create SyslogWriter instance with temporary directory"""
    writer = SyslogWriter(log_dir=temp_log_dir)
    yield writer
    writer.close()


@pytest.fixture
def message_deduplicator() -> MessageDeduplicatorTestAdapter:
    """Create MessageDeduplicator adapter instance with short window for testing (for unit tests only)"""
    return MessageDeduplicatorTestAdapter(window_minutes=1)


@pytest.fixture
def real_message_deduplicator() -> MessageDeduplicator:
    """Create real MessageDeduplicator instance for integration tests"""
    return MessageDeduplicator(window_minutes=1)


@pytest.fixture
def udp_receiver_with_port(
    syslog_writer: SyslogWriter, 
    real_message_deduplicator: MessageDeduplicator
) -> Generator[Tuple[UDPSyslogReceiver, int], None, None]:
    """Create UDP receiver on available port"""
    # Find available port
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    
    receiver = UDPSyslogReceiver(
        host='127.0.0.1',
        port=port,
        writer=syslog_writer,
        deduplicator=real_message_deduplicator
    )
    
    # Start receiver in background thread
    thread = threading.Thread(target=receiver.start, daemon=True)
    thread.start()
    
    # Wait for receiver to be ready
    max_wait = 1.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if receiver.running:
            break
        time.sleep(0.05)
    
    time.sleep(0.1)  # Additional small delay
    
    yield receiver, port
    
    receiver.stop()
    time.sleep(0.1)  # Give it time to stop


@pytest.fixture
def tls_receiver_with_port(
    syslog_writer: SyslogWriter,
    real_message_deduplicator: MessageDeduplicator,
    temp_log_dir: str
) -> Generator[Tuple[TLSSyslogReceiver, int, str, str], None, None]:
    """Create TLS receiver on available port with self-signed certificates"""
    # Find available port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    
    # Generate temporary certificates
    cert_file = os.path.join(temp_log_dir, 'test_cert.pem')
    key_file = os.path.join(temp_log_dir, 'test_key.pem')
    
    receiver = TLSSyslogReceiver(
        host='127.0.0.1',
        port=port,
        cert_file=cert_file,
        key_file=key_file,
        writer=syslog_writer,
        deduplicator=real_message_deduplicator
    )
    
    # Start receiver in background thread
    thread = threading.Thread(target=receiver.start, daemon=True)
    thread.start()
    
    # Wait for receiver to be ready (cert generation + server start)
    max_wait = 3.0  # seconds
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if receiver.running:
            # Try to connect to verify server is listening
            try:
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_sock.settimeout(0.1)
                test_sock.connect(('127.0.0.1', port))
                test_sock.close()
                break
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(0.1)
        else:
            time.sleep(0.1)
    
    # Additional small delay to ensure SSL context is ready
    time.sleep(0.2)
    
    yield receiver, port, cert_file, key_file
    
    receiver.stop()
    time.sleep(0.1)


@pytest.fixture
def sample_syslog_messages() -> dict:
    """Sample syslog messages for testing various scenarios"""
    return {
        'rfc3164_emergency': '<8>Jan 15 10:30:45 server1 kernel: System panic - critical failure',
        'rfc3164_alert': '<9>Jan 15 10:30:46 server1 security: Intrusion detected from 192.168.1.100',
        'rfc3164_critical': '<10>Jan 15 10:30:47 server1 db: Database connection lost',
        'rfc3164_error': '<11>Jan 15 10:30:48 server1 app: Failed to process request',
        'rfc3164_warning': '<12>Jan 15 10:30:49 server1 app: Slow query detected (5.2s)',
        'rfc3164_notice': '<13>Jan 15 10:30:50 server1 app: Configuration reload completed',
        'rfc3164_info': '<14>Jan 15 10:30:51 server1 app: User logged in: admin',
        'rfc3164_debug': '<15>Jan 15 10:30:52 server1 app: Debug: Processing item 42',
        
        'rfc5424_emergency': '<8>1 2025-11-17T10:30:45.123Z server1 kernel 1234 - - System panic',
        'rfc5424_with_structured': '<14>1 2025-11-17T10:30:45.123Z web01 nginx 5678 REQ [request@12345 method="GET" path="/api/users" status="200"] Request completed',
        
        'malformed_no_priority': 'Jan 15 10:30:45 server1 app: Missing priority tag',
        'malformed_invalid_priority': '<>Jan 15 10:30:45 server1 app: Empty priority',
        'malformed_high_priority': '<999>Jan 15 10:30:45 server1 app: Priority too high',
        
        'long_message': f'<14>Jan 15 10:30:45 server1 app: {"A" * 5000}',  # 5KB message
        'unicode_message': '<14>Jan 15 10:30:45 server1 app: Unicode test: 你好世界 🚀',
        
        'empty': '',
        'whitespace_only': '   \n\t  ',
    }


@pytest.fixture
def real_world_log_samples() -> dict:
    """Real-world log message examples from various systems"""
    return {
        'nginx_access': '<14>Jan 15 10:30:45 web01 nginx: 192.168.1.100 - - [15/Jan/2025:10:30:45 +0000] "GET /api/v1/users HTTP/1.1" 200 1234 "-" "Mozilla/5.0"',
        'apache_error': '<11>Jan 15 10:30:45 web02 apache2: [error] [client 192.168.1.100:54321] File does not exist: /var/www/html/favicon.ico',
        'mysql_error': '<11>Jan 15 10:30:45 db01 mysqld: [ERROR] InnoDB: Cannot allocate memory for the buffer pool',
        'postgresql_log': '<14>Jan 15 10:30:45 db02 postgres: LOG:  checkpoint complete: wrote 1234 buffers (0.3%); 0 transaction log file(s) added, 0 removed, 1 recycled; write=0.123 s, sync=0.045 s, total=0.234 s',
        'ssh_auth_success': '<14>Jan 15 10:30:45 server1 sshd[12345]: Accepted publickey for admin from 192.168.1.50 port 54321 ssh2: RSA SHA256:abc123def456',
        'ssh_auth_failure': '<12>Jan 15 10:30:45 server1 sshd[12346]: Failed password for invalid user hacker from 203.0.113.100 port 54322 ssh2',
        'kernel_oom': '<8>Jan 15 10:30:45 server1 kernel: Out of memory: Kill process 12345 (java) score 789 or sacrifice child',
        'systemd_service': '<14>Jan 15 10:30:45 server1 systemd[1]: Started My Application Service.',
        'docker_container': '<14>Jan 15 10:30:45 server1 dockerd: container 1234abcd5678 started',
        'firewall_block': '<12>Jan 15 10:30:45 fw01 kernel: [UFW BLOCK] IN=eth0 OUT= MAC=00:11:22:33:44:55 SRC=203.0.113.100 DST=192.168.1.10 PROTO=TCP SPT=12345 DPT=22',
        'cron_job': '<14>Jan 15 10:30:45 server1 CRON[12345]: (root) CMD (/usr/local/bin/backup.sh)',
    }


@pytest.fixture
def performance_test_config() -> dict:
    """Configuration for performance testing"""
    return {
        'burst_count': 100,  # Messages in burst
        'sustained_rate': 50,  # Messages per second
        'duration': 5,  # Seconds
        'concurrent_connections': 10,
    }

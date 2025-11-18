"""Real-world scenario tests simulating production conditions"""

import json
import os
import socket
import ssl
import threading
import time
from typing import Tuple

import pytest


class TestHighLoadScenarios:
    """Tests simulating high-load production scenarios"""
    
    def test_burst_traffic_udp(
        self,
        udp_receiver_with_port: Tuple,
        temp_log_dir: str,
        performance_test_config: dict
    ):
        """Test handling burst of UDP messages (simulates traffic spike)"""
        receiver, port = udp_receiver_with_port
        burst_count = performance_test_config['burst_count']
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        start_time = time.time()
        
        # Send burst of messages as fast as possible
        for i in range(burst_count):
            msg = f'<14>Jan 15 10:30:45 server1 app: Burst message {i}'
            sock.sendto(msg.encode(), ('127.0.0.1', port))
        
        end_time = time.time()
        sock.close()
        
        # Wait for processing
        time.sleep(1.0)
        
        # Verify all messages received
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()
            received_count = len(lines)
        
        # Should receive at least 95% of messages (allow for some UDP loss)
        assert received_count >= burst_count * 0.95, \
            f"Expected ~{burst_count} messages, got {received_count}"
        
        duration = end_time - start_time
        rate = burst_count / duration
        print(f"\\nBurst test: Sent {burst_count} messages in {duration:.2f}s ({rate:.0f} msg/s)")
    
    def test_sustained_load_udp(
        self,
        udp_receiver_with_port: Tuple,
        temp_log_dir: str,
        performance_test_config: dict
    ):
        """Test sustained message rate over time (simulates steady production load)"""
        receiver, port = udp_receiver_with_port
        
        rate = performance_test_config['sustained_rate']  # Messages per second
        duration = performance_test_config['duration']  # Seconds
        expected_total = rate * duration
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        interval = 1.0 / rate  # Time between messages
        
        start_time = time.time()
        sent_count = 0
        
        while time.time() - start_time < duration:
            # Make each message unique to avoid deduplication
            msg = f'<14>Jan 15 10:30:45 server1 app{sent_count}: Sustained message {sent_count}'
            sock.sendto(msg.encode(), ('127.0.0.1', port))
            sent_count += 1
            time.sleep(interval)
        
        sock.close()
        time.sleep(0.5)
        
        # Verify messages received
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            received_count = len(f.readlines())
        
        # Should receive at least 80% of messages (UDP can drop packets under load)
        assert received_count >= expected_total * 0.80, \
            f"Expected ~{expected_total} messages, got {received_count}"
        
        print(f"\\nSustained test: {sent_count} messages over {duration}s ({rate} msg/s target)")
    
    def test_concurrent_clients_tls(
        self,
        tls_receiver_with_port: Tuple,
        temp_log_dir: str,
        performance_test_config: dict
    ):
        """Test many concurrent TLS connections (simulates multi-client production)"""
        receiver, port, cert_file, key_file = tls_receiver_with_port
        num_clients = performance_test_config['concurrent_connections']
        messages_per_client = 10
        
        results = {'success': 0, 'failed': 0}
        lock = threading.Lock()
        
        def tls_client(client_id: int):
            try:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                
                with socket.create_connection(('127.0.0.1', port), timeout=10) as sock:
                    with context.wrap_socket(sock) as ssock:
                        for i in range(messages_per_client):
                            # Make each message unique with client_id and message number
                            raw_msg = f'<14>1 2025-11-17T10:30:45.123Z server1 client{client_id} 1234 - - Client {client_id} Message {i}'
                            length = len(raw_msg)
                            message = f'{length} {raw_msg}'
                            ssock.sendall(message.encode())
                            time.sleep(0.01)
                
                with lock:
                    results['success'] += 1
            except Exception as e:
                with lock:
                    results['failed'] += 1
                print(f"Client {client_id} failed: {e}")
        
        # Launch concurrent clients
        start_time = time.time()
        threads = [
            threading.Thread(target=tls_client, args=(i,))
            for i in range(num_clients)
        ]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=30)
        
        duration = time.time() - start_time
        
        # Wait for processing
        time.sleep(1.0)
        
        # Verify results
        assert results['success'] >= num_clients * 0.90, \
            f"Only {results['success']}/{num_clients} clients succeeded"
        
        expected_messages = results['success'] * messages_per_client
        
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            received_count = len(f.readlines())
        
        # Allow 5% message loss
        assert received_count >= expected_messages * 0.95, \
            f"Expected ~{expected_messages} messages, got {received_count}"
        
        print(f"\\nConcurrent test: {num_clients} clients, {results['success']} succeeded in {duration:.2f}s")


class TestNetworkFailureScenarios:
    """Tests simulating network failures and resilience"""
    
    def test_connection_timeout_recovery(
        self,
        tls_receiver_with_port: Tuple
    ):
        """Test recovery from connection timeout"""
        receiver, port, cert_file, key_file = tls_receiver_with_port
        
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Establish connection but don't send data (simulate slow client)
        with socket.create_connection(('127.0.0.1', port)) as sock:
            sock.settimeout(2.0)
            with context.wrap_socket(sock) as ssock:
                # Hold connection open without sending
                time.sleep(3.0)
        
        # Receiver should still work after timeout
        time.sleep(0.2)
        
        # Send valid message
        with socket.create_connection(('127.0.0.1', port)) as sock:
            with context.wrap_socket(sock) as ssock:
                raw_msg = '<14>1 2025-11-17T10:30:45.123Z server1 app 1234 - - Recovery test'
                length = len(raw_msg)
                message = f'{length} {raw_msg}'
                ssock.sendall(message.encode())
        
        time.sleep(0.2)
        assert receiver.running is True
    
    def test_partial_message_handling_tls(
        self,
        tls_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test handling of partial/incomplete messages over TLS"""
        receiver, port, cert_file, key_file = tls_receiver_with_port
        
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection(('127.0.0.1', port)) as sock:
            with context.wrap_socket(sock) as ssock:
                # Send partial octet count (incomplete message)
                ssock.sendall(b'100 <14>1 2025-11-17T10:30:45')
                time.sleep(0.2)
                
                # Connection drop before complete message
        
        time.sleep(0.2)
        
        # Receiver should still work - send complete message
        with socket.create_connection(('127.0.0.1', port)) as sock:
            with context.wrap_socket(sock) as ssock:
                raw_msg = '<14>1 2025-11-17T10:30:45.123Z server1 app 1234 - - Complete message'
                length = len(raw_msg)
                message = f'{length} {raw_msg}'
                ssock.sendall(message.encode())
        
        time.sleep(0.2)
        
        # Should have received the complete message
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            data = json.loads(f.readline())
            assert 'Complete message' in data['message']
    
    def test_rapid_reconnections(
        self,
        tls_receiver_with_port: Tuple
    ):
        """Test handling rapid connection/disconnection cycles"""
        receiver, port, cert_file, key_file = tls_receiver_with_port
        
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Rapidly connect and disconnect 20 times
        for i in range(20):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=2) as sock:
                    with context.wrap_socket(sock) as ssock:
                        raw_msg = f'<14>1 2025-11-17T10:30:45.123Z server1 app 1234 - - Rapid connection {i}'
                        length = len(raw_msg)
                        message = f'{length} {raw_msg}'
                        ssock.sendall(message.encode())
                # Immediate disconnect
            except Exception as e:
                pytest.fail(f"Connection {i} failed: {e}")
        
        time.sleep(0.3)
        assert receiver.running is True


class TestMalformedDataScenarios:
    """Tests for handling malformed and edge-case data"""
    
    def test_oversized_udp_message(
        self,
        udp_receiver_with_port: Tuple
    ):
        """Test handling UDP message larger than typical MTU"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Create 10KB message (larger than typical 1500 byte MTU)
        large_content = 'A' * 10000
        msg = f'<14>Jan 15 10:30:45 server1 app: {large_content}'
        
        try:
            sock.sendto(msg.encode(), ('127.0.0.1', port))
        except Exception as e:
            # OS may reject very large UDP packets
            print(f"Large UDP send failed (expected): {e}")
        
        sock.close()
        time.sleep(0.2)
        
        # Receiver should still be running
        assert receiver.running is True
    
    def test_invalid_octet_count_tls(
        self,
        tls_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test handling invalid octet count in TLS stream"""
        receiver, port, cert_file, key_file = tls_receiver_with_port
        
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection(('127.0.0.1', port)) as sock:
            with context.wrap_socket(sock) as ssock:
                # Send message with incorrect octet count
                raw_msg = '<14>1 2025-11-17T10:30:45.123Z server1 app 1234 - - Test'
                wrong_length = 999  # Much larger than actual
                message = f'{wrong_length} {raw_msg}'
                
                ssock.sendall(message.encode())
                time.sleep(0.5)
                
                # Send valid message to verify recovery
                raw_msg2 = '<14>1 2025-11-17T10:30:45.123Z server1 app 1234 - - Valid after invalid'
                correct_length = len(raw_msg2)
                message2 = f'{correct_length} {raw_msg2}'
                ssock.sendall(message2.encode())
        
        time.sleep(0.3)
    
    def test_non_utf8_content(
        self,
        udp_receiver_with_port: Tuple
    ):
        """Test handling non-UTF-8 encoded content"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Send message with invalid UTF-8 sequences
        invalid_utf8 = b'<14>Jan 15 10:30:45 server1 app: Invalid UTF-8: \\xff\\xfe'
        
        try:
            sock.sendto(invalid_utf8, ('127.0.0.1', port))
        except Exception:
            pass  # May fail, which is acceptable
        
        sock.close()
        time.sleep(0.2)
        
        # Receiver should still work
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        valid_msg = '<14>Jan 15 10:30:45 server1 app: Valid UTF-8 after invalid'
        sock.sendto(valid_msg.encode(), ('127.0.0.1', port))
        sock.close()
        
        time.sleep(0.2)
        assert receiver.running is True
    
    def test_sql_injection_attempts(
        self,
        udp_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test that SQL injection attempts are safely logged"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Common SQL injection patterns
        injection_attempts = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM passwords--",
        ]
        
        for attempt in injection_attempts:
            msg = f'<12>Jan 15 10:30:45 web01 app: Login attempt with username: {attempt}'
            sock.sendto(msg.encode(), ('127.0.0.1', port))
            time.sleep(0.05)
        
        sock.close()
        time.sleep(0.3)
        
        # Verify messages logged safely (as strings, not executed)
        log_file = os.path.join(temp_log_dir, 'warning.log')
        with open(log_file, 'r') as f:
            for line in f:
                data = json.loads(line)
                # Injection attempt should be in message as string
                assert any(attempt in data['message'] for attempt in injection_attempts)
    
    def test_control_characters(
        self,
        udp_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test handling messages with control characters"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Message with various control characters
        msg = '<14>Jan 15 10:30:45 server1 app: Control chars: \\x00\\x01\\x02\\t\\n\\r'
        sock.sendto(msg.encode('unicode_escape'), ('127.0.0.1', port))
        sock.close()
        
        time.sleep(0.2)
        
        # Should handle gracefully without crashing
        assert receiver.running is True


class TestProductionWorkflowSimulation:
    """End-to-end tests simulating real production workflows"""
    
    def test_web_server_log_workflow(
        self,
        udp_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Simulate web server logging workflow with access and error logs"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Simulate web traffic: successful requests
        for i in range(50):
            msg = f'<14>Jan 15 10:30:{i:02d} web01 nginx: 192.168.1.{i%256} - - "GET /api/v1/users/{i} HTTP/1.1" 200 {1000+i*10}'
            sock.sendto(msg.encode(), ('127.0.0.1', port))
            time.sleep(0.02)
        
        # Simulate errors (404s)
        for i in range(10):
            msg = f'<12>Jan 15 10:31:{i:02d} web01 nginx: 192.168.1.{i%256} - - "GET /api/v1/missing/{i} HTTP/1.1" 404 123'
            sock.sendto(msg.encode(), ('127.0.0.1', port))
            time.sleep(0.02)
        
        # Simulate critical errors (500s)
        for i in range(5):
            msg = f'<11>Jan 15 10:32:{i:02d} web01 nginx: 192.168.1.{i%256} - - "POST /api/v1/process HTTP/1.1" 500 456'
            sock.sendto(msg.encode(), ('127.0.0.1', port))
            time.sleep(0.02)
        
        sock.close()
        time.sleep(0.5)
        
        # Verify proper categorization by severity
        info_file = os.path.join(temp_log_dir, 'info.log')
        warning_file = os.path.join(temp_log_dir, 'warning.log')
        error_file = os.path.join(temp_log_dir, 'error.log')
        
        with open(info_file, 'r') as f:
            info_count = len(f.readlines())
        
        with open(warning_file, 'r') as f:
            warning_count = len(f.readlines())
        
        with open(error_file, 'r') as f:
            error_count = len(f.readlines())
        
        assert info_count >= 45  # Allow some UDP loss
        assert warning_count >= 9
        assert error_count >= 4
        
        print(f"\\nWeb server simulation: Info={info_count}, Warning={warning_count}, Error={error_count}")
    
    def test_database_monitoring_workflow(
        self,
        udp_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Simulate database monitoring with various log levels"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Normal operations (info)
        for i in range(20):
            msg = f'<14>Jan 15 10:30:{i:02d} db01 postgres: LOG: checkpoint complete: wrote {100+i} buffers'
            sock.sendto(msg.encode(), ('127.0.0.1', port))
            time.sleep(0.05)
        
        # Slow queries (warning)
        for i in range(5):
            msg = f'<12>Jan 15 10:35:{i:02d} db01 postgres: WARNING: query took {5+i}.{i}s to complete'
            sock.sendto(msg.encode(), ('127.0.0.1', port))
            time.sleep(0.05)
        
        # Connection errors (error)
        for i in range(3):
            # Make each error unique to avoid deduplication
            msg = f'<11>Jan 15 10:40:{i:02d} db01 postgres: ERROR: connection limit exceeded (attempt {i})'
            sock.sendto(msg.encode(), ('127.0.0.1', port))
            time.sleep(0.05)
        
        # Critical issue (critical)
        msg = '<10>Jan 15 10:45:00 db01 postgres: CRITICAL: disk space low, database may shut down'
        sock.sendto(msg.encode(), ('127.0.0.1', port))
        
        sock.close()
        time.sleep(0.5)
        
        # Verify all severity levels present
        severity_counts = {}
        for severity in ['info', 'warning', 'error', 'critical']:
            log_file = os.path.join(temp_log_dir, f'{severity}.log')
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    severity_counts[severity] = len(f.readlines())
        
        assert severity_counts.get('info', 0) >= 18
        assert severity_counts.get('warning', 0) >= 4
        assert severity_counts.get('error', 0) >= 2
        assert severity_counts.get('critical', 0) >= 1
        
        print(f"\\nDatabase simulation: {severity_counts}")

"""Integration tests for UDP and TLS syslog receivers"""

import json
import os
import socket
import ssl
import time
from typing import Tuple

import pytest


class TestUDPReceiverIntegration:
    """Integration tests for UDP syslog receiver"""
    
    def test_udp_receive_single_message(
        self, 
        udp_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test receiving a single UDP message end-to-end"""
        receiver, port = udp_receiver_with_port
        
        # Send message via UDP
        message = '<14>Jan 15 10:30:45 server1 app: Test UDP message'
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(message.encode(), ('127.0.0.1', port))
        sock.close()
        
        # Wait for processing
        time.sleep(0.2)
        
        # Verify message written to file
        log_file = os.path.join(temp_log_dir, 'info.log')
        assert os.path.exists(log_file)
        
        with open(log_file, 'r') as f:
            data = json.loads(f.readline())
            assert 'Test UDP message' in data['message']
            assert data['severity'] == 'info'
    
    def test_udp_receive_multiple_messages(
        self,
        udp_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test receiving multiple UDP messages"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Send 10 different messages
        for i in range(10):
            message = f'<14>Jan 15 10:30:45 server1 app: Message {i}'
            sock.sendto(message.encode(), ('127.0.0.1', port))
            time.sleep(0.01)
        
        sock.close()
        time.sleep(0.3)
        
        # Verify all messages written
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 10
            
            for i, line in enumerate(lines):
                data = json.loads(line)
                assert f'Message {i}' in data['message']
    
    def test_udp_different_severities(
        self,
        udp_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test UDP messages with different severity levels"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Send messages with different severities
        test_cases = [
            (8, 'emergency', 'emergency.log'),
            (11, 'error', 'error.log'),
            (12, 'warning', 'warning.log'),
            (14, 'info', 'info.log'),
        ]
        
        for priority, severity, filename in test_cases:
            message = f'<{priority}>Jan 15 10:30:45 server1 app: {severity} message'
            sock.sendto(message.encode(), ('127.0.0.1', port))
            time.sleep(0.05)
        
        sock.close()
        time.sleep(0.2)
        
        # Verify each severity file created
        for priority, severity, filename in test_cases:
            log_file = os.path.join(temp_log_dir, filename)
            assert os.path.exists(log_file), f"Missing {filename}"
            
            with open(log_file, 'r') as f:
                data = json.loads(f.readline())
                assert data['severity'] == severity
    
    def test_udp_duplicate_suppression(
        self,
        udp_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test that duplicate messages are suppressed"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Send same message 5 times
        duplicate_msg = '<14>Jan 15 10:30:45 server1 app: Duplicate test'
        for _ in range(5):
            sock.sendto(duplicate_msg.encode(), ('127.0.0.1', port))
            time.sleep(0.1)
        
        sock.close()
        time.sleep(0.3)
        
        # Should only have 1 message written
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 1, f"Expected 1 message (deduplication), got {len(lines)}"
    
    def test_udp_malformed_message_handling(
        self,
        udp_receiver_with_port: Tuple
    ):
        """Test handling of malformed UDP messages"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Send various malformed messages - should not crash receiver
        malformed = [
            b'',  # Empty
            b'<>Invalid',
            b'<999>Priority too high',
            b'No priority tag',
            b'\x00\x01\x02\xff',  # Binary data
        ]
        
        for msg in malformed:
            try:
                sock.sendto(msg, ('127.0.0.1', port))
                time.sleep(0.05)
            except Exception as e:
                pytest.fail(f"Sending malformed message caused exception: {e}")
        
        sock.close()
        
        # Receiver should still be running
        time.sleep(0.2)
        
        # Send valid message to confirm receiver still works
        valid_msg = '<14>Jan 15 10:30:45 server1 app: Valid after malformed'
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(valid_msg.encode(), ('127.0.0.1', port))
        sock.close()
        time.sleep(0.2)
        
        # Should still process valid messages
        assert receiver.running is True


class TestTLSReceiverIntegration:
    """Integration tests for TLS syslog receiver"""
    
    def test_tls_receive_single_message(
        self,
        tls_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test receiving a single TLS message with octet counting"""
        receiver, port, cert_file, key_file = tls_receiver_with_port
        
        # Create TLS connection
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # Self-signed cert
        
        with socket.create_connection(('127.0.0.1', port)) as sock:
            with context.wrap_socket(sock) as ssock:
                # Send octet-counted message
                raw_msg = '<14>1 2025-11-17T10:30:45.123Z server1 app 1234 - - TLS test message'
                length = len(raw_msg)
                message = f'{length} {raw_msg}'
                
                ssock.sendall(message.encode())
                time.sleep(0.2)
        
        # Verify message written
        log_file = os.path.join(temp_log_dir, 'info.log')
        assert os.path.exists(log_file)
        
        with open(log_file, 'r') as f:
            data = json.loads(f.readline())
            assert 'TLS test message' in data['message']
    
    def test_tls_receive_multiple_messages_single_connection(
        self,
        tls_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test receiving multiple messages over single TLS connection"""
        receiver, port, cert_file, key_file = tls_receiver_with_port
        
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection(('127.0.0.1', port)) as sock:
            with context.wrap_socket(sock) as ssock:
                # Send multiple octet-counted messages
                for i in range(5):
                    raw_msg = f'<14>1 2025-11-17T10:30:45.123Z server1 app 1234 - - TLS message {i}'
                    length = len(raw_msg)
                    message = f'{length} {raw_msg}'
                    
                    ssock.sendall(message.encode())
                    time.sleep(0.1)
                
                time.sleep(0.2)
        
        # Verify all messages written
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 5
            
            for i, line in enumerate(lines):
                data = json.loads(line)
                assert f'TLS message {i}' in data['message']
    
    def test_tls_concurrent_connections(
        self,
        tls_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test handling multiple concurrent TLS connections"""
        import threading
        
        receiver, port, cert_file, key_file = tls_receiver_with_port
        
        def send_tls_message(client_id: int):
            # Small delay to stagger connections
            time.sleep(client_id * 0.05)
            
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=5) as sock:
                    with context.wrap_socket(sock) as ssock:
                        # Make each message unique to avoid deduplication
                        raw_msg = f'<14>1 2025-11-17T10:30:45.123Z server1 client{client_id} 1234 - - Concurrent TLS message {client_id}'
                        length = len(raw_msg)
                        message = f'{length} {raw_msg}'
                        
                        ssock.sendall(message.encode())
                        time.sleep(0.1)
            except Exception as e:
                pytest.fail(f"Client {client_id} failed: {e}")
        
        # Create 5 concurrent connections
        threads = [
            threading.Thread(target=send_tls_message, args=(i,))
            for i in range(5)
        ]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=10)
        
        time.sleep(0.5)
        
        # Verify all messages received
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 5, f"Expected 5 messages, got {len(lines)}"
    
    def test_tls_connection_resilience(
        self,
        tls_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test that receiver handles connection drops gracefully"""
        receiver, port, cert_file, key_file = tls_receiver_with_port
        
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Send message, close abruptly
        with socket.create_connection(('127.0.0.1', port)) as sock:
            with context.wrap_socket(sock) as ssock:
                raw_msg = '<14>1 2025-11-17T10:30:45.123Z server1 app 1234 - - Message before drop'
                length = len(raw_msg)
                message = f'{length} {raw_msg}'
                ssock.sendall(message.encode())
                # Drop connection immediately
        
        time.sleep(0.2)
        
        # Receiver should still work - send another message
        with socket.create_connection(('127.0.0.1', port)) as sock:
            with context.wrap_socket(sock) as ssock:
                raw_msg = '<14>1 2025-11-17T10:30:45.123Z server1 app 1234 - - Message after drop'
                length = len(raw_msg)
                message = f'{length} {raw_msg}'
                ssock.sendall(message.encode())
        
        time.sleep(0.2)
        
        # Both messages should be received
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) >= 2


class TestReceiverRealWorldScenarios:
    """Real-world scenario tests combining multiple aspects"""
    
    def test_mixed_udp_tls_traffic(
        self,
        udp_receiver_with_port: Tuple,
        tls_receiver_with_port: Tuple,
        temp_log_dir: str
    ):
        """Test receiving messages from both UDP and TLS simultaneously"""
        udp_receiver, udp_port = udp_receiver_with_port
        tls_receiver, tls_port, cert_file, key_file = tls_receiver_with_port
        
        # Send UDP messages
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for i in range(5):
            msg = f'<14>Jan 15 10:30:45 server1 udp_app: UDP message {i}'
            udp_sock.sendto(msg.encode(), ('127.0.0.1', udp_port))
            time.sleep(0.05)
        udp_sock.close()
        
        # Send TLS messages
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection(('127.0.0.1', tls_port)) as sock:
            with context.wrap_socket(sock) as ssock:
                for i in range(5):
                    raw_msg = f'<14>1 2025-11-17T10:30:45.123Z server1 tls_app 1234 - - TLS message {i}'
                    length = len(raw_msg)
                    message = f'{length} {raw_msg}'
                    ssock.sendall(message.encode())
                    time.sleep(0.05)
        
        time.sleep(0.3)
        
        # Verify both types of messages received
        log_file = os.path.join(temp_log_dir, 'info.log')
        with open(log_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 10  # 5 UDP + 5 TLS
            
            udp_count = sum(1 for line in lines if 'UDP message' in line)
            tls_count = sum(1 for line in lines if 'TLS message' in line)
            
            assert udp_count == 5
            assert tls_count == 5
    
    def test_real_world_log_samples(
        self,
        udp_receiver_with_port: Tuple,
        temp_log_dir: str,
        real_world_log_samples: dict
    ):
        """Test processing real-world log message samples"""
        receiver, port = udp_receiver_with_port
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Send all real-world samples
        for sample_name, message in real_world_log_samples.items():
            sock.sendto(message.encode(), ('127.0.0.1', port))
            time.sleep(0.05)
        
        sock.close()
        time.sleep(0.3)
        
        # Verify messages processed (check various log files)
        log_files = [f for f in os.listdir(temp_log_dir) if f.endswith('.log')]
        assert len(log_files) > 0, "No log files created"
        
        # Count total messages across all severity files
        total_messages = 0
        for log_file in log_files:
            with open(os.path.join(temp_log_dir, log_file), 'r') as f:
                total_messages += len(f.readlines())
        
        assert total_messages == len(real_world_log_samples), \
            f"Expected {len(real_world_log_samples)} messages, got {total_messages}"

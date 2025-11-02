#!/usr/bin/env python3
"""
Syslog Receiver Application - Main Entry Point
Receives syslog messages over UDP or TLS, parses them, and writes to severity-based log files.
Includes deduplication logic to prevent duplicate messages within a 10-minute window.
"""

import logging
import os
import threading
import time

from msg_deduplicator import MessageDeduplicator
from syslog_writer import SyslogWriter
from tls_syslog_receiver import TLSSyslogReceiver
from udp_syslog_receiver import UDPSyslogReceiver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point"""
    # Configuration from environment variables
    udp_port = int(os.environ.get('SYSLOG_UDP_PORT', '514'))
    tls_port = int(os.environ.get('SYSLOG_TLS_PORT', '6514'))
    log_dir = os.environ.get('SYSLOG_LOG_DIR', 'logs')
    cert_file = os.environ.get('SYSLOG_CERT_FILE', 'cert.pem')
    key_file = os.environ.get('SYSLOG_KEY_FILE', 'key.pem')
    enable_udp = os.environ.get('SYSLOG_ENABLE_UDP', 'true').lower() == 'true'
    enable_tls = os.environ.get('SYSLOG_ENABLE_TLS', 'true').lower() == 'true'
    
    logger.info("Starting Syslog Receiver Application")
    logger.info(f"UDP Port: {udp_port} (enabled: {enable_udp})")
    logger.info(f"TLS Port: {tls_port} (enabled: {enable_tls})")
    logger.info(f"Log Directory: {log_dir}")
    
    # Initialize components
    writer = SyslogWriter(log_dir=log_dir)
    deduplicator = MessageDeduplicator(window_minutes=10)
    
    receivers = []
    
    # Start UDP receiver
    if enable_udp:
        udp_receiver = UDPSyslogReceiver(
            port=udp_port,
            writer=writer,
            deduplicator=deduplicator
        )
        udp_thread = threading.Thread(target=udp_receiver.start, daemon=True)
        udp_thread.start()
        receivers.append(udp_receiver)
    
    # Start TLS receiver
    if enable_tls:
        tls_receiver = TLSSyslogReceiver(
            port=tls_port,
            cert_file=cert_file,
            key_file=key_file,
            writer=writer,
            deduplicator=deduplicator
        )
        tls_thread = threading.Thread(target=tls_receiver.start, daemon=True)
        tls_thread.start()
        receivers.append(tls_receiver)
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        for receiver in receivers:
            receiver.stop()
        writer.close()


if __name__ == '__main__':
    main()

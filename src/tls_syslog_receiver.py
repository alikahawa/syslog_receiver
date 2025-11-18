import logging
import select
import socket
import ssl
import threading
from datetime import datetime
from typing import List, Optional, Tuple

from .octet_counting_reader import OctetCountingReader
from .syslog_parser import SyslogParser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TLSSyslogReceiver:
    """Receive syslog messages over TLS with support for multiple connections"""
    
    def __init__(self, host: str = '0.0.0.0', port: int = 6514, 
                 cert_file: str = 'cert.pem', key_file: str = 'key.pem',
                 writer: Optional[object] = None, deduplicator: Optional[object] = None) -> None:
        self.host: str = host
        self.port: int = port
        self.cert_file: str = cert_file
        self.key_file: str = key_file
        self.writer: Optional[object] = writer
        self.deduplicator: Optional[object] = deduplicator
        self.running: bool = False
        self.connections: List[Tuple[ssl.SSLSocket, threading.Thread]] = []
        self.lock: threading.Lock = threading.Lock()
    
    def start(self) -> None:
        """Start the TLS syslog receiver"""
        self.running = True
        
        # Create SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        
        try:
            context.load_cert_chain(self.cert_file, self.key_file)
        except FileNotFoundError:
            logger.warning(f"Certificate files not found at {self.cert_file}. Generating self-signed certificate...")
            # Generate in same directory as requested cert file
            import os
            cert_dir = os.path.dirname(self.cert_file) or '.'
            os.makedirs(cert_dir, exist_ok=True)
            self._generate_self_signed_cert(self.cert_file, self.key_file)
            # Paths are already correct, load the certs
            context.load_cert_chain(self.cert_file, self.key_file)
        
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(5)
        sock.setblocking(False)
        
        logger.info(f"TLS syslog receiver listening on {self.host}:{self.port}")
        
        # Accept connections
        while self.running:
            try:
                readable, _, _ = select.select([sock], [], [], 1.0)
                if readable:
                    client_sock, client_addr = sock.accept()
                    logger.info(f"New connection from {client_addr}")
                    
                    # Wrap socket with TLS
                    try:
                        tls_sock = context.wrap_socket(client_sock, server_side=True)
                        tls_sock.setblocking(False)
                        
                        # Start handler thread
                        handler = threading.Thread(
                            target=self._handle_connection,
                            args=(tls_sock, client_addr),
                            daemon=True
                        )
                        handler.start()
                        
                        with self.lock:
                            self.connections.append((tls_sock, handler))
                    except ssl.SSLError as e:
                        logger.error(f"SSL error with {client_addr}: {e}")
                        client_sock.close()
                        
            except Exception as e:
                if self.running:
                    logger.error(f"Error accepting connection: {e}")
        
        sock.close()
 
    def _handle_connection(self, sock: ssl.SSLSocket, addr: Tuple[str, int]) -> None:
        """Handle a single TLS connection"""
        reader = OctetCountingReader()
        
        try:
            while self.running:
                readable, _, _ = select.select([sock], [], [], 1.0)
                if not readable:
                    continue
                
                try:
                    data = sock.recv(4096)
                    if not data:
                        logger.info(f"Connection closed by {addr}")
                        break
                    
                    # Process octet-counted messages
                    messages = reader.feed(data)
                    for message in messages:
                        self._process_message(message, addr[0])
                        
                except ssl.SSLWantReadError:
                    continue
                except Exception as e:
                    logger.error(f"Error reading from {addr}: {e}")
                    break
                    
        finally:
            try:
                sock.close()
            except Exception:
                pass
            logger.info(f"Connection handler for {addr} terminated")
 
    def _process_message(self, message: str, source_ip: str) -> None:
        """Process a single syslog message"""
        parsed = SyslogParser.parse(message)
        
        # Check for duplicates
        if self.deduplicator:
            priority = parsed.get('priority', 0)
            msg_content = parsed.get('message', '')
            if not self.deduplicator.should_write(source_ip, priority, msg_content):
                return
        
        # Add source IP to parsed data
        parsed['source_ip'] = source_ip
        parsed['received_at'] = datetime.utcnow().isoformat()
        
        # Write to file
        if self.writer:
            self.writer.write(parsed)
    
    def _generate_self_signed_cert(self, cert_path: str, key_path: str) -> None:
        """Generate a self-signed certificate for testing"""
        from subprocess import PIPE, run
        
        logger.info(f"Generating self-signed certificate at {cert_path}...")
        cmd = [
            'openssl', 'req', '-x509', '-newkey', 'rsa:4096',
            '-keyout', key_path, '-out', cert_path,
            '-days', '365', '-nodes',
            '-subj', '/CN=localhost'
        ]
        
        result = run(cmd, stdout=PIPE, stderr=PIPE)
        if result.returncode != 0:
            logger.error(f"Failed to generate certificate: {result.stderr.decode()}")
            raise Exception("Could not generate self-signed certificate")
        
        logger.info(f"Self-signed certificate generated successfully at {cert_path}")

    def stop(self) -> None:
        """Stop the receiver"""
        self.running = False
        with self.lock:
            for sock, _ in self.connections:
                try:
                    sock.close()
                except Exception:
                    pass



import logging
import socket
from datetime import datetime
from typing import Optional

from .syslog_parser import SyslogParser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UDPSyslogReceiver:
    """Receive syslog messages over UDP"""
    
    def __init__(self, host: str = '0.0.0.0', port: int = 514, 
                 writer: Optional[object] = None, deduplicator: Optional[object] = None) -> None:
        """
        Initialize UDP syslog receiver.
        
        Args:
            host: Interface to bind to
                  - '0.0.0.0' = All interfaces (default, required for containers)
                  - '127.0.0.1' = Localhost only (development)
                  - Specific IP = Single interface (production on bare metal)
            port: UDP port to listen on (default: 514)
            writer: Optional SyslogWriter instance
            deduplicator: Optional deduplicator instance
        
        Security Note:
            When using 0.0.0.0 (all interfaces), ensure proper firewall rules
            or security groups are configured to restrict access to trusted sources.
            In containerized environments (Docker/ECS), this is typically handled
            by the orchestration platform's network policies.
        """
        self.host: str = host
        self.port: int = port
        self.writer: Optional[object] = writer
        self.deduplicator: Optional[object] = deduplicator
        self.running: bool = False
    
    def start(self) -> None:
        """Start the UDP syslog receiver"""
        self.running = True
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.host, self.port))
        sock.settimeout(1.0)
        
        logger.info(f"UDP syslog receiver listening on {self.host}:{self.port}")
        
        while self.running:
            try:
                data, addr = sock.recvfrom(65535)
                message = data.decode('utf-8', errors='replace')
                self._process_message(message, addr[0])
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error receiving UDP message: {e}")
        
        sock.close()
    
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
        parsed['received_at'] = datetime.now().isoformat()
        
        # Write to file
        if self.writer:
            self.writer.write(parsed)
    
    def stop(self) -> None:
        """Stop the receiver"""
        self.running = False



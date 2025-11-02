import logging
from typing import List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OctetCountingReader:
    """Handle octet-counted framing for syslog messages over TCP/TLS"""
    
    def __init__(self) -> None:
        self.buffer: bytes = b''
    
    def feed(self, data: bytes) -> List[str]:
        """
        Feed data into the buffer and yield complete messages.
        Handles octet-counted framing: "<length> <message>"
        """
        self.buffer += data
        messages: List[str] = []
        
        while self.buffer:
            # Try to read the length prefix
            space_idx = self.buffer.find(b' ')
            if space_idx == -1:
                # Not enough data yet
                break
            
            try:
                length_str = self.buffer[:space_idx].decode('ascii')
                message_length = int(length_str)
            except (ValueError, UnicodeDecodeError):
                # Invalid length, try to recover by skipping this byte
                logger.warning("Invalid octet count, attempting to recover")
                self.buffer = self.buffer[1:]
                continue
            
            # Check if we have the complete message
            frame_length = space_idx + 1 + message_length
            if len(self.buffer) < frame_length:
                # Not enough data yet
                break
            
            # Extract the message
            message_start = space_idx + 1
            message_end = message_start + message_length
            message = self.buffer[message_start:message_end]
            
            # Remove processed data from buffer
            self.buffer = self.buffer[frame_length:]
            
            try:
                messages.append(message.decode('utf-8'))
            except UnicodeDecodeError as e:
                logger.error(f"Error decoding message: {e}")
        
        return messages



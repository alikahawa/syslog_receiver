import logging
from typing import List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OctetCountingReader:
    """Handle octet-counted framing for syslog messages over TCP/TLS"""
    
    MAX_BUFFER_SIZE = 10 * 1024 * 1024  # 10 MB
    MAX_MESSAGE_LENGTH = 65535  # 64KB
    
    def __init__(self,
                 max_msg_len: int = MAX_MESSAGE_LENGTH,
                 max_buffer_size: int = MAX_BUFFER_SIZE) -> None:
        self.buffer: bytes = b''
        self.max_msg_len = max_msg_len
        self.max_buffer_size = max_buffer_size
    
    def feed(self, data: bytes) -> List[str]:
        """Feed data and return complete messages"""
        self.buffer += data
        
        if not self._check_buffer_size():
            return []
        
        return self._extract_all_messages()
    
    def _check_buffer_size(self) -> bool:
        """Internal: Check buffer doesn't exceed limit"""
        if len(self.buffer) > self.max_buffer_size:
            logger.error(f"Buffer overflow: {len(self.buffer)} bytes, resetting")
            self.buffer = b''
            return False
        return True
    
    def _extract_all_messages(self) -> List[str]:
        """Internal: Extract all complete messages from buffer"""
        messages: List[str] = []
        
        while self.buffer:
            result = self._try_extract_one_message()
            if result is None:
                # There is no data!
                break 
            if isinstance(result, str):
                # If result is False, skip to next iteration (recovery)
                messages.append(result)
        
        return messages
    
    def _try_extract_one_message(self) -> str | bool | None:
        """
        Try to extract one message.
        Returns: str (message), None (need more data), False (skip/recovery)
        """
        space_idx = self.buffer.find(b' ')
        if space_idx == -1:
            return None
        
        # Parse length
        try:
            message_length = int(self.buffer[:space_idx].decode('ascii'))
        except (ValueError, UnicodeDecodeError):
            logger.warning("Invalid octet count, skipping byte")
            self.buffer = self.buffer[1:]
            return False  # Recovery mode
        
        # Validate length
        if message_length > self.max_msg_len:
            logger.warning(f"Message too large: {message_length}, skipping")
            self._skip_to_next_frame(space_idx)
            return False
        
        # Check completeness
        frame_length = space_idx + 1 + message_length
        if len(self.buffer) < frame_length:
            return None
        
        return self._extract_and_decode(space_idx, message_length, frame_length)
    
    def _skip_to_next_frame(self, space_idx: int) -> None:
        """Internal: Skip malformed frame"""
        next_newline = self.buffer.find(b'\n', space_idx)
        if next_newline > 0:
            self.buffer = self.buffer[next_newline+1:]
        else:
            self.buffer = b''
    
    def _extract_and_decode(self, space_idx: int, msg_len: int, frame_len: int) -> str:
        """Internal: Extract message bytes and decode to string"""
        msg_start = space_idx + 1
        msg_end = msg_start + msg_len
        msg_bytes = self.buffer[msg_start:msg_end]
        
        self.buffer = self.buffer[frame_len:]
        
        try:
            return msg_bytes.decode('utf-8')
        except UnicodeDecodeError as e:
            logger.warning(f"UTF-8 error, using replacement: {e}")
            return msg_bytes.decode('utf-8', errors='replace')


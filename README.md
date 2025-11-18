# syslog_receiver
As part of an assessment for a job application, I was tasked with developing a Python application capable of receiving, parsing, and storing syslog messages over UDP and TLS. The solution needed to support multiple concurrent connections, implement automatic deduplication, and provide severity-based log routing.

This system supports multiple protocols, including UDP on port 514 and TLS on port 6514. It is fully RFC compliant, capable of parsing both RFC 5424 and RFC 3164 syslog formats.
For TCP and TLS streams, it handles octet-counted framing efficiently.
To maintain data integrity, it includes message deduplication, preventing duplicate entries within a 10-minute window.
Messages are routed based on severity, with each severity level written to separate files.
Security is ensured through TLS encryption, and the system can automatically generate self-signed certificates.
It is designed to manage multiple simultaneous TLS connections and properly handle short reads on TCP connections.
All messages are stored in structured JSON format for easy processing.
Additionally, the solution is container-ready, providing a Dockerfile and Docker Compose configuration, and includes Terraform scripts for seamless deployment on AWS ECS Fargate.

**Notes**:
- Terraform code has not been tested!
- AI was used to help making the process faster and to increase the productivity

## Prerequisites

-   Docker and Docker Compose
-   Python 3.11+ (for local development)

For testing:
- Open-ssl
- network-tools

Optional:
-   Terraform for cloud deployment
-   AWS CLI configured (for cloud deployment)

## Quick Start

### Using Makefile
To use this option please install `make`

```bash
# 1. Build and run
make dev

# 2. In another terminal, send test messages
make test

# 3. View the logs
ls -la logs/
cat logs/info.log | jq .

# 4. Watch real-time logs
make dev-logs

# 5. Stop when done
make stop
```

### Docker

1. **Build the image**

    ```bash
    docker build -t syslog-receiver:latest .
    ```

2. **Run with Docker Compose**

    ```bash
    docker-compose up -d
    ```

3. **View logs**

    ```bash
    docker-compose logs -f
    ```

4. **Check output files**
    ```bash
    ls -la logs/
    cat logs/info.log
    ```

### Local Development

1. **Clone the repository**

    ```bash
    git clone git@github.com:alikahawa/syslog_receiver.git
    cd syslog_receiver
    ```

2. **Run**

    ```bash
    python3 src/main.py
    ```

3. **Test with logger** 
    Open a new terminal and run the following to test the logger:

    ```bash
    # UDP test
    logger -n localhost -P 514 "Test message over UDP"

    # TCP test (requires proper certificate setup)
    logger -n localhost -P 6514 --tcp "Test message over TCP"
    ```

    ```bash
    # Run locally
    make dev

    # Generate test traffic
    while true; do
      logger -n localhost -P 514 "Test message $(date)"
      sleep 1
    done

    # Watch logs
    watch -n 1 'tail -5 logs/info.log | jq .'
    ```
## Cloud Deployment

### AWS (ECS Fargate)

Complete Terraform configuration is provided in the `terraform/` directory.

```bash
cd terraform

# Initialize Terraform
terraform init

# Review plan
terraform plan

# Deploy
terraform apply

# Get endpoints
terraform output nlb_dns_name
terraform output udp_endpoint
terraform output tls_endpoint
```

See `terraform/README.md` for detailed deployment instructions.


## Configuration

The application is configured via environment variables:

| Variable            | Default  | Description                    |
| ------------------- | -------- | ------------------------------ |
| `SYSLOG_UDP_PORT`   | 514      | UDP port to listen on          |
| `SYSLOG_TLS_PORT`   | 6514     | TLS port to listen on          |
| `SYSLOG_LOG_DIR`    | logs     | Directory for output log files |
| `SYSLOG_CERT_FILE`  | cert.pem | Path to TLS certificate        |
| `SYSLOG_KEY_FILE`   | key.pem  | Path to TLS private key        |
| `SYSLOG_ENABLE_UDP` | true     | Enable UDP receiver            |
| `SYSLOG_ENABLE_TLS` | true     | Enable TLS receiver            |

## Output Files

Messages are written to separate files based on severity:

-   `emergency.log` - System is unusable
-   `alert.log` - Action must be taken immediately
-   `critical.log` - Critical conditions
-   `error.log` - Error conditions
-   `warning.log` - Warning conditions
-   `notice.log` - Normal but significant condition
-   `info.log` - Informational messages
-   `debug.log` - Debug-level messages

Each line in the log files is a JSON object with the following structure:

```json
{
    "priority": 13,
    "facility": "user",
    "severity": "notice",
    "timestamp": "2025-10-31T12:00:00",
    "hostname": "server01",
    "message": "Test message",
    "source_ip": "192.168.1.100",
    "received_at": "2025-10-31T12:00:00.123456",
    "format": "RFC3164",
    "raw": "<13>Oct 31 12:00:00 server01 Test message"
}
```

## Message Deduplication

The application implements intelligent deduplication based on:

-   Source IP address
-   Message priority
-   Message content

If identical messages (same source, priority, and content) are received within a 10-minute window, only the first message is written to disk. This prevents log flooding while preserving unique messages.

## Architecture

### Components

1. **SyslogParser**: Parses RFC 3164 and RFC 5424 formatted messages
2. **MessageDeduplicator**: Tracks and prevents duplicate messages
3. **SyslogWriter**: Writes messages to severity-based log files
4. **OctetCountingReader**: Handles octet-counted framing for TCP/TLS
5. **UDPSyslogReceiver**: Receives messages over UDP
6. **TLSSyslogReceiver**: Receives messages over TLS with connection multiplexing

### Flow

```
Syslog Source (rsyslog/syslog-ng)
         |
         | UDP/TLS
         v
  Syslog Receiver
         |
         +--> Parser (RFC 3164/5424)
         |
         +--> Deduplicator
         |
         +--> Writer (severity-based routing)
         |
         v
   Log Files (JSON)
```


# Explinations

## OctetCountingReader

### What is Octet-Counting? (RFC 6587)
Octet-counting is a framing method for syslog messages transmitted over TCP/TLS.
It solves a fundamental problem: "Where does one message end and the next begin?"
`Message1Message2Message3...`

TCP is a byte stream protocol - there are no message boundaries!
When syslog is sent over TCP, messages are part of a continuous stream:

```
Send:     "Hello" + "World"
Receive:  "Hel"   "loWor"   "ld"    (TCP can split anywhere!)
```

We need a way to tell where each message starts/ends.

We have two Framing Methods
1. Method 1: Newline Delimiter (Traditional): it is Simple, but if message contains \n? Message gets split!
2. Method 2: Octet-Counting (RFC 6587). Format: <length><space><message>
    - Count the exact number of bytes in the message
    - Prefix the message with: length + space
    - Send: length<space>message
    - As a result: we know exactly how many bytes to read!

Anatomy of a Frame in Octect-Counting:

```bash
48 <34>Oct 11 22:14:15 server app: Hello World
│  │└────────────────────────────────────────┘
│  │              48 bytes 
│  └─ Space (delimiter)
└─ Length prefix (ASCII digits)
```

### Example:

We get the following input:

```python3
data = b'48 <34>Oct 11 22:14:15 server app: Hello World'
reader.feed(data)
```

First we buffer the incoming data since TCP might deliver the data as chuncks, after that we check the buffer size limit.
Then we look for the space index so that we can process the message and read its length. 

```bash
b'48 <34>Oct 11 22:14:15 server app: Hello World'
  ↑
  Position 2 (space_idx)
```

We then extract the length of the data:

```bash
b'48 <34>Oct 11 22:14:15 server app: Hello World'
 ↑↑
 Extract these 2 bytes → '48'
```

From here, we check the message in the rest of the buffer since we now know the length of the message, if a message is incomplete we handle it as a partial frame.
After that we continue to the next one in the while loop.
We also do validate the buffers to ensure that the length of the message or the size of the buffer does not exceed the predefind size to protect against memory attacks.



# Tests
## Test Pyramid Structure

```
                    ▲
                   / \
                  /   \
                 /     \
                /       \
               /  E2E    \         13 tests (~30s)
              / Scenarios \       Production simulations
             /_____________\
            /               \
           /  Integration    \     11 tests (~10s)
          /    Tests          \    UDP/TLS receivers
         /___________________  \
        /                       \
       /       Unit Tests        \   48 tests (~2s)
      /   Parser, Writer, Dedup   \  Fast, isolated
     /_____________________________\

Total: 72 tests
```

## Running Tests

### Prerequisites

```bash
# Install test dependencies
pip install -r requirements.txt

# Or install just pytest
pip install pytest pytest-cov pytest-timeout pytest-xdist
```

### Basic Test Execution

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_syslog_parser.py

# Run specific test class
pytest tests/test_integration.py::TestUDPReceiverIntegration

# Run specific test method
pytest tests/test_syslog_parser.py::TestSyslogParserRFC3164::test_parse_all_severity_levels
```

### Test Categories with Markers

```bash
# Run only unit tests (fast)
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only scenario tests
pytest -m scenario

# Exclude slow tests
pytest -m "not slow"
```

### Coverage Reports

```bash
# Run tests with coverage
pytest --cov=src --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux

# Generate terminal coverage report
pytest --cov=src --cov-report=term-missing
```


# What's next?
- Metrics & Monitoring - Add Prometheus endpoint for observability
- REST API - For configuration, stats, and modern log ingestion
- Message Enrichment - GeoIP, DNS lookups
- Streaming Output - Kafka/Kinesis for real-time processing

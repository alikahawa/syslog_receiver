#!/bin/bash

# Test script for syslog receiver
# This script sends various test messages to verify functionality
#
# Usage:
#   ./test_syslog.sh                          # Test localhost (assumes service is running)
#   ./test_syslog.sh --docker                 # Start Docker Compose, test, then stop
#   ./test_syslog.sh --docker-keep            # Start Docker Compose, test, keep running
#   ./test_syslog.sh <host> [udp_port] [tls_port]  # Test remote host

set -e

# Parse arguments
START_DOCKER=false
STOP_DOCKER=false
HOST="localhost"
UDP_PORT="514"
TLS_PORT="6514"

if [[ "$1" == "--docker" ]]; then
    START_DOCKER=true
    STOP_DOCKER=true
    HOST="localhost"
    UDP_PORT="514"
    TLS_PORT="6514"
elif [[ "$1" == "--docker-keep" ]]; then
    START_DOCKER=true
    STOP_DOCKER=false
    HOST="localhost"
    UDP_PORT="514"
    TLS_PORT="6514"
else
    HOST="${1:-localhost}"
    UDP_PORT="${2:-514}"
    TLS_PORT="${3:-6514}"
fi

if [ "$START_DOCKER" = true ]; then
    echo "==> Starting Docker Compose..."
    docker-compose up -d
    sleep 5
    echo ""
fi

# Cleanup function
cleanup() {
    if [ "$STOP_DOCKER" = true ]; then
        echo ""
        echo "==> Stopping Docker Compose..."
        docker-compose down
    fi
}

# Register cleanup on exit if we started Docker
if [ "$STOP_DOCKER" = true ]; then
    trap cleanup EXIT
fi

echo "Testing Syslog Receiver at ${HOST}"
echo "UDP Port: ${UDP_PORT}"
echo "TLS Port: ${TLS_PORT}"
echo ""

# Detect TLS-capable client
TLS_CLIENT=""
if command -v ncat &> /dev/null; then
    TLS_CLIENT="ncat"
    echo "✓ TLS client: ncat (with SSL support)"
elif command -v openssl &> /dev/null; then
    TLS_CLIENT="openssl"
    echo "✓ TLS client: openssl s_client"
else
    echo "⚠ Warning: No TLS-capable client found (ncat/openssl)"
    echo "  TLS tests will be skipped or may fail"
fi
echo ""

# Function to send TLS message with proper client
send_tls() {
    local message="$1"
    if [ "$TLS_CLIENT" = "ncat" ]; then
        echo "$message" | ncat --ssl --no-shutdown "${HOST}" "${TLS_PORT}" 2>/dev/null
    elif [ "$TLS_CLIENT" = "openssl" ]; then
        echo "$message" | openssl s_client -connect "${HOST}:${TLS_PORT}" -quiet -no_ign_eof 2>/dev/null
    else
        echo "$message" | nc -w1 "${HOST}" "${TLS_PORT}" 2>/dev/null
        return 1
    fi
}

# Test counters for verification
MESSAGES_SENT=0

# Test UDP messages - Basic severity levels
echo "==> Testing UDP messages (RFC 3164 - Basic Severity Levels)..."
for severity in 0 1 2 3 4 5 6 7; do
    priority=$((8 + severity))  # user facility (1) << 3 + severity
    timestamp=$(date '+%b %d %H:%M:%S')
    hostname=$(hostname)
    msg="<${priority}>${timestamp} ${hostname} test[$$]: Test message with severity ${severity}"
    
    echo "Sending: ${msg}"
    echo "${msg}" | nc -u -w1 "${HOST}" "${UDP_PORT}"
    ((MESSAGES_SENT++))
    sleep 0.1
done

echo ""
echo "==> Testing multiple facilities with different severities..."
# Test daemon facility (3)
for severity in 0 3 6; do
    priority=$((24 + severity))  # daemon facility (3) << 3 + severity
    timestamp=$(date '+%b %d %H:%M:%S')
    hostname=$(hostname)
    msg="<${priority}>${timestamp} ${hostname} daemon[$$]: Daemon message severity ${severity}"
    
    echo "Sending: ${msg}"
    echo "${msg}" | nc -u -w1 "${HOST}" "${UDP_PORT}"
    ((MESSAGES_SENT++))
    sleep 0.1
done

# Test local0 facility (16) - commonly used for custom apps
for severity in 1 4 7; do
    priority=$((128 + severity))  # local0 facility (16) << 3 + severity
    timestamp=$(date '+%b %d %H:%M:%S')
    hostname=$(hostname)
    msg="<${priority}>${timestamp} ${hostname} myapp[$$]: Local0 application message severity ${severity}"
    
    echo "Sending: ${msg}"
    echo "${msg}" | nc -u -w1 "${HOST}" "${UDP_PORT}"
    ((MESSAGES_SENT++))
    sleep 0.1
done

# Test local7 facility (23) - often used for custom apps
for severity in 2 5; do
    priority=$((184 + severity))  # local7 facility (23) << 3 + severity
    timestamp=$(date '+%b %d %H:%M:%S')
    hostname=$(hostname)
    msg="<${priority}>${timestamp} ${hostname} custom-app[$$]: Local7 custom message severity ${severity}"
    
    echo "Sending: ${msg}"
    echo "${msg}" | nc -u -w1 "${HOST}" "${UDP_PORT}"
    ((MESSAGES_SENT++))
    sleep 0.1
done

echo ""
echo "==> Testing message length variations..."
# Short message (under 50 chars)
priority=14  # user.info
timestamp=$(date '+%b %d %H:%M:%S')
hostname=$(hostname)
msg="<${priority}>${timestamp} ${hostname} test[$$]: Short"
echo "Sending short message (${#msg} chars): ${msg}"
echo "${msg}" | nc -u -w1 "${HOST}" "${UDP_PORT}"
((MESSAGES_SENT++))
sleep 0.1

# Medium message (~200 chars)
medium_text="This is a medium length message designed to test the parser's ability to handle messages of typical length. It contains enough text to be realistic but not so much as to be unwieldy."
msg="<${priority}>${timestamp} ${hostname} test[$$]: ${medium_text}"
echo "Sending medium message (${#msg} chars)"
echo "${msg}" | nc -u -w1 "${HOST}" "${UDP_PORT}"
((MESSAGES_SENT++))
sleep 0.1

# Long message (~1KB)
long_text="This is a very long message intended to stress test the syslog receiver's ability to handle large payloads. "
long_text+="It contains repeated text to reach approximately 1KB in size. "
for i in {1..10}; do
    long_text+="Iteration ${i}: The quick brown fox jumps over the lazy dog. Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
done
msg="<${priority}>${timestamp} ${hostname} test[$$]: ${long_text}"
echo "Sending long message (${#msg} chars)"
echo "${msg}" | nc -u -w1 "${HOST}" "${UDP_PORT}"
((MESSAGES_SENT++))
sleep 0.1

echo ""
echo "==> Testing RFC 5424 format messages (structured syslog)..."
# RFC 5424 format: <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG
for severity in 0 3 6; do
    priority=$((8 + severity))  # user facility
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%S.000Z)
    hostname=$(hostname)
    msg="<${priority}>1 ${timestamp} ${hostname} testapp $$ MSG${severity} - RFC5424 message with severity ${severity}"
    
    echo "Sending RFC 5424: ${msg}"
    echo "${msg}" | nc -u -w1 "${HOST}" "${UDP_PORT}"
    ((MESSAGES_SENT++))
    sleep 0.1
done

# RFC 5424 with structured data
priority=14  # user.info
timestamp=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%S.000Z)
hostname=$(hostname)
msg="<${priority}>1 ${timestamp} ${hostname} webapp $$ REQ001 [request@12345 method=\"GET\" path=\"/api/users\" status=\"200\"] Request completed successfully"
echo "Sending RFC 5424 with structured data: ${msg}"
echo "${msg}" | nc -u -w1 "${HOST}" "${UDP_PORT}"
((MESSAGES_SENT++))
sleep 0.1

echo ""
echo "==> Testing duplicate message suppression (UDP)..."
DUPLICATE_MSG="<13>$(date '+%b %d %H:%M:%S') $(hostname) test[$$]: Duplicate test message"
for i in {1..5}; do
    echo "Sending duplicate ${i}/5"
    echo "${DUPLICATE_MSG}" | nc -u -w1 "${HOST}" "${UDP_PORT}"
    if [ $i -eq 1 ]; then
        ((MESSAGES_SENT++))  # Only first should be written
    fi
    sleep 0.5
done
echo "Note: Only the first duplicate should be written to logs (deduplication test)"

echo ""
echo "==> Testing TLS messages with octet counting (RFC 5424 format)..."
for severity in 0 3 6; do
    priority=$((8 + severity))
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%S.000Z)
    hostname=$(hostname)
    raw_msg="<${priority}>1 ${timestamp} ${hostname} test $$ - - TLS test message with severity ${severity}"
    length=$(echo -n "${raw_msg}" | wc -c | tr -d ' ')
    msg="${length} ${raw_msg}"
    
    echo "Sending octet-counted message over TLS (length: ${length})"
    if send_tls "${msg}"; then
        echo "  ✓ Sent successfully"
    else
        echo "  ⚠ TLS connection failed (may need proper TLS client)"
    fi
    ((MESSAGES_SENT++))
    sleep 0.1
done

echo ""
echo "==> Testing TLS concurrent connections (multiple simultaneous clients)..."
# Function to send TLS message in background
send_tls_message() {
    local severity=$1
    local client_id=$2
    priority=$((8 + severity))
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%S.000Z)
    hostname=$(hostname)
    raw_msg="<${priority}>1 ${timestamp} ${hostname} client${client_id} $$ - - Concurrent TLS connection ${client_id} with severity ${severity}"
    length=$(echo -n "${raw_msg}" | wc -c | tr -d ' ')
    msg="${length} ${raw_msg}"
    
    send_tls "${msg}" &
}

# Launch 5 concurrent connections
echo "Launching 5 concurrent TLS connections..."
for i in {1..5}; do
    severity=$((i % 8))
    send_tls_message ${severity} ${i} &
    ((MESSAGES_SENT++))
done

# Wait for all background jobs to complete
wait
echo "All concurrent connections completed"

echo ""
echo "==> Testing TLS with multiple messages in single connection..."
# Send multiple messages over one connection using a here-doc
{
    for severity in 0 2 4 6; do
        priority=$((8 + severity))
        timestamp=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%S.000Z)
        hostname=$(hostname)
        raw_msg="<${priority}>1 ${timestamp} ${hostname} persistent $$ - - Message ${severity} in persistent connection"
        length=$(echo -n "${raw_msg}" | wc -c | tr -d ' ')
        echo "${length} ${raw_msg}"
        ((MESSAGES_SENT++))
        sleep 0.1
    done
} > /tmp/tls_batch_msgs_$$.txt

if [ "$TLS_CLIENT" = "ncat" ]; then
    ncat --ssl --no-shutdown "${HOST}" "${TLS_PORT}" < /tmp/tls_batch_msgs_$$.txt 2>/dev/null && echo "  ✓ Sent successfully" || echo "  ⚠ TLS connection failed"
elif [ "$TLS_CLIENT" = "openssl" ]; then
    openssl s_client -connect "${HOST}:${TLS_PORT}" -quiet -no_ign_eof < /tmp/tls_batch_msgs_$$.txt 2>/dev/null && echo "  ✓ Sent successfully" || echo "  ⚠ TLS connection failed"
else
    nc -w2 "${HOST}" "${TLS_PORT}" < /tmp/tls_batch_msgs_$$.txt 2>/dev/null || echo "  ⚠ TLS connection may require proper TLS client"
fi

rm -f /tmp/tls_batch_msgs_$$.txt
echo "Sent 4 messages over single persistent TLS connection"

echo ""
echo "==> Test complete!"
echo ""
echo "Total unique messages sent: ${MESSAGES_SENT}"
echo "(Note: 4 duplicate messages were sent but should not be written)"
echo ""

# Automated output verification
echo "==> Performing automated verification..."
sleep 2  # Give the receiver time to write files

LOGS_DIR="logs"
if [ "$START_DOCKER" = true ]; then
    # Create temp directory for verification
    mkdir -p /tmp/syslog-test-verify
    docker cp $(docker-compose ps -q syslog-receiver):/app/logs/. /tmp/syslog-test-verify/ 2>/dev/null || {
        echo "Note: Could not copy logs from container for verification"
        LOGS_DIR="/tmp/syslog-test-verify"
    }
    LOGS_DIR="/tmp/syslog-test-verify"
fi

if [ -d "${LOGS_DIR}" ]; then
    echo ""
    echo "Verification Results:"
    echo "-------------------"
    
    # Check each severity file
    for severity_file in emergency.log alert.log critical.log error.log warning.log notice.log info.log debug.log; do
        if [ -f "${LOGS_DIR}/${severity_file}" ]; then
            count=$(wc -l < "${LOGS_DIR}/${severity_file}" | tr -d ' ')
            
            # Validate JSON format
            if command -v jq >/dev/null 2>&1; then
                if jq empty "${LOGS_DIR}/${severity_file}" 2>/dev/null; then
                    echo "✓ ${severity_file}: ${count} messages (valid JSON)"
                else
                    echo "✗ ${severity_file}: ${count} messages (INVALID JSON)"
                fi
            else
                echo "  ${severity_file}: ${count} messages (jq not available for JSON validation)"
            fi
        fi
    done
    
    echo ""
    echo "Expected: ~${MESSAGES_SENT} unique messages across all files"
    
    # Count total messages
    total_messages=0
    for severity_file in emergency.log alert.log critical.log error.log warning.log notice.log info.log debug.log; do
        if [ -f "${LOGS_DIR}/${severity_file}" ]; then
            count=$(wc -l < "${LOGS_DIR}/${severity_file}" | tr -d ' ')
            total_messages=$((total_messages + count))
        fi
    done
    echo "Actual: ${total_messages} messages written"
    
    if [ ${total_messages} -eq ${MESSAGES_SENT} ]; then
        echo "✓ Message count matches (deduplication working correctly)"
    else
        echo "⚠ Message count mismatch (expected ${MESSAGES_SENT}, got ${total_messages})"
    fi
    
    # Cleanup temp directory
    if [ "$START_DOCKER" = true ]; then
        rm -rf /tmp/syslog-test-verify
    fi
else
    echo "Logs directory not found at ${LOGS_DIR}"
    echo "Verification skipped"
fi

echo ""

if [ "$START_DOCKER" = true ]; then
    echo "Docker container logs (last 30 lines):"
    docker-compose logs --tail=30 syslog-receiver
    echo ""
fi

echo "To manually check results, examine the log files:"
if [ "$START_DOCKER" = true ]; then
    echo "  docker-compose exec syslog-receiver ls -la /app/logs/"
    echo "  docker-compose exec syslog-receiver cat /app/logs/info.log | jq ."
    echo "  docker-compose exec syslog-receiver cat /app/logs/error.log | jq ."
    echo ""
    echo "Or locally (if volume is mounted):"
fi
echo "  ls -la logs/"
echo "  cat logs/info.log | jq ."
echo "  cat logs/error.log | jq ."

if [ "$STOP_DOCKER" = false ] && [ "$START_DOCKER" = true ]; then
    echo ""
    echo "Docker Compose is still running. To stop:"
    echo "  docker-compose down"
fi


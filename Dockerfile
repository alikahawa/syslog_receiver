FROM python:3.12-slim

# Install OpenSSL for certificate generation
RUN apt-get update && \
    apt-get install -y --no-install-recommends openssl && \
    rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Create logs directory
RUN mkdir -p /app/logs

# Copy application code
COPY src/ /app/src/

# Create non-root user for security
RUN useradd -r -u 1000 -g 0 syslog && \
    chown -R syslog:0 /app && \
    chmod -R g+w /app

USER syslog

# Expose ports
# 514 for UDP syslog
# 6514 for TLS syslog
EXPOSE 514/udp 6514/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD test -d /app/logs || exit 1

# Set environment variables
ENV SYSLOG_UDP_PORT=514
ENV SYSLOG_TLS_PORT=6514
ENV SYSLOG_LOG_DIR=/app/logs
ENV SYSLOG_CERT_FILE=/app/cert.pem
ENV SYSLOG_KEY_FILE=/app/key.pem
ENV SYSLOG_ENABLE_UDP=true
ENV SYSLOG_ENABLE_TLS=true

# Run the application
CMD ["python", "-u", "src/main.py"]

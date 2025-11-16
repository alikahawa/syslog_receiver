# Network Load Balancer
resource "aws_lb" "syslog_nlb" {
  name               = "syslog-receiver-nlb"
  internal           = false
  load_balancer_type = "network"
  subnets            = aws_subnet.public[*].id
  
  enable_deletion_protection       = false
  enable_cross_zone_load_balancing = true
  
  tags = {
    Name = "syslog-receiver-nlb"
  }
}

# Target Group for UDP Syslog
resource "aws_lb_target_group" "syslog_udp" {
  name        = "syslog-udp-tg"
  port        = 514
  protocol    = "UDP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"
  
  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    interval            = 30
    protocol            = "TCP"
    port                = 6514
  }
  
  deregistration_delay = 30
  
  tags = {
    Name = "syslog-udp-tg"
  }
}

# Target Group for TLS Syslog
resource "aws_lb_target_group" "syslog_tls" {
  name        = "syslog-tls-tg"
  port        = 6514
  protocol    = "TCP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"
  
  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    interval            = 30
    protocol            = "TCP"
    port                = 6514
  }
  
  deregistration_delay = 30
  
  tags = {
    Name = "syslog-tls-tg"
  }
}

# Listener for UDP Syslog
resource "aws_lb_listener" "syslog_udp" {
  load_balancer_arn = aws_lb.syslog_nlb.arn
  port              = 514
  protocol          = "UDP"
  
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.syslog_udp.arn
  }
}

# Listener for TLS Syslog
resource "aws_lb_listener" "syslog_tls" {
  load_balancer_arn = aws_lb.syslog_nlb.arn
  port              = 6514
  protocol          = "TCP"
  
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.syslog_tls.arn
  }
}

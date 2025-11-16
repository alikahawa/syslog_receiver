# Security Group for ECS Tasks
resource "aws_security_group" "ecs_tasks" {
  name_prefix = "syslog-receiver-ecs-"
  description = "Security group for syslog receiver ECS tasks"
  vpc_id      = aws_vpc.main.id
  
  ingress {
    description     = "UDP syslog from NLB"
    from_port       = 514
    to_port         = 514
    protocol        = "udp"
    security_groups = [aws_security_group.nlb.id]
  }
  
  ingress {
    description     = "TLS syslog from NLB"
    from_port       = 6514
    to_port         = 6514
    protocol        = "tcp"
    security_groups = [aws_security_group.nlb.id]
  }
  
  ingress {
    description = "NFS from VPC for EFS"
    from_port   = 2049
    to_port     = 2049
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "syslog-receiver-ecs-sg"
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

# Security Group for Network Load Balancer
resource "aws_security_group" "nlb" {
  name_prefix = "syslog-receiver-nlb-"
  description = "Security group for syslog receiver NLB"
  vpc_id      = aws_vpc.main.id
  
  ingress {
    description = "UDP syslog"
    from_port   = 514
    to_port     = 514
    protocol    = "udp"
    cidr_blocks = var.allowed_cidr_blocks
  }
  
  ingress {
    description = "TLS syslog"
    from_port   = 6514
    to_port     = 6514
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }
  
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "syslog-receiver-nlb-sg"
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

# Security Group for EFS
resource "aws_security_group" "efs" {
  count       = var.enable_efs ? 1 : 0
  name_prefix = "syslog-receiver-efs-"
  description = "Security group for syslog receiver EFS"
  vpc_id      = aws_vpc.main.id
  
  ingress {
    description     = "NFS from ECS tasks"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }
  
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "syslog-receiver-efs-sg"
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

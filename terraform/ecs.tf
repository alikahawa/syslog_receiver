# ECR Repository
resource "aws_ecr_repository" "syslog_receiver" {
  name                 = "syslog-receiver"
  image_tag_mutability = "MUTABLE"
  
  image_scanning_configuration {
    scan_on_push = true
  }
  
  encryption_configuration {
    encryption_type = "AES256"
  }
  
  tags = {
    Name = "syslog-receiver"
  }
}

# ECR Lifecycle Policy
resource "aws_ecr_lifecycle_policy" "syslog_receiver" {
  repository = aws_ecr_repository.syslog_receiver.name
  
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images older than 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ECS Cluster
resource "aws_ecs_cluster" "syslog" {
  name = "syslog-receiver-cluster"
  
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  
  tags = {
    Name = "syslog-receiver-cluster"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "syslog_receiver" {
  name              = "/ecs/syslog-receiver"
  retention_in_days = var.log_retention_days
  
  tags = {
    Name = "syslog-receiver-logs"
  }
}

# ECS Task Execution Role
resource "aws_iam_role" "ecs_execution" {
  name = "syslog-receiver-ecs-execution-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
  
  tags = {
    Name = "syslog-receiver-ecs-execution-role"
  }
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional policy for ECR access
resource "aws_iam_role_policy" "ecs_execution_ecr" {
  name = "ecr-access"
  role = aws_iam_role.ecs_execution.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      }
    ]
  })
}

# ECS Task Role
resource "aws_iam_role" "ecs_task" {
  name = "syslog-receiver-ecs-task-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
  
  tags = {
    Name = "syslog-receiver-ecs-task-role"
  }
}

# ECS Task Definition
resource "aws_ecs_task_definition" "syslog_receiver" {
  family                   = "syslog-receiver"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.container_cpu
  memory                   = var.container_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  
  container_definitions = jsonencode([
    {
      name      = "syslog-receiver"
      image     = "${aws_ecr_repository.syslog_receiver.repository_url}:latest"
      essential = true
      
      portMappings = [
        {
          containerPort = 514
          protocol      = "udp"
        },
        {
          containerPort = 6514
          protocol      = "tcp"
        }
      ]
      
      environment = [
        {
          name  = "SYSLOG_UDP_PORT"
          value = "514"
        },
        {
          name  = "SYSLOG_TLS_PORT"
          value = "6514"
        },
        {
          name  = "SYSLOG_LOG_DIR"
          value = "/app/logs"
        },
        {
          name  = "SYSLOG_ENABLE_UDP"
          value = "true"
        },
        {
          name  = "SYSLOG_ENABLE_TLS"
          value = "true"
        }
      ]
      
      mountPoints = var.enable_efs ? [
        {
          sourceVolume  = "efs-logs"
          containerPath = "/app/logs"
          readOnly      = false
        }
      ] : []
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.syslog_receiver.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      
      healthCheck = {
        command     = ["CMD-SHELL", "test -d /app/logs || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])
  
  dynamic "volume" {
    for_each = var.enable_efs ? [1] : []
    content {
      name = "efs-logs"
      
      efs_volume_configuration {
        file_system_id     = aws_efs_file_system.syslog_logs[0].id
        transit_encryption = "ENABLED"
        
        authorization_config {
          access_point_id = aws_efs_access_point.syslog_logs[0].id
        }
      }
    }
  }
  
  tags = {
    Name = "syslog-receiver-task"
  }
}

# ECS Service
resource "aws_ecs_service" "syslog_receiver" {
  name            = "syslog-receiver"
  cluster         = aws_ecs_cluster.syslog.id
  task_definition = aws_ecs_task_definition.syslog_receiver.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }
  
  load_balancer {
    target_group_arn = aws_lb_target_group.syslog_udp.arn
    container_name   = "syslog-receiver"
    container_port   = 514
  }
  
  load_balancer {
    target_group_arn = aws_lb_target_group.syslog_tls.arn
    container_name   = "syslog-receiver"
    container_port   = 6514
  }
  
  depends_on = [
    aws_lb_listener.syslog_udp,
    aws_lb_listener.syslog_tls
  ]
  
  tags = {
    Name = "syslog-receiver-service"
  }
}

# Auto Scaling Target
resource "aws_appautoscaling_target" "ecs" {
  max_capacity       = 10
  min_capacity       = var.desired_count
  resource_id        = "service/${aws_ecs_cluster.syslog.name}/${aws_ecs_service.syslog_receiver.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Auto Scaling Policy - CPU
resource "aws_appautoscaling_policy" "ecs_cpu" {
  name               = "syslog-receiver-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace
  
  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Auto Scaling Policy - Memory
resource "aws_appautoscaling_policy" "ecs_memory" {
  name               = "syslog-receiver-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace
  
  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value       = 80.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# EFS File System for persistent log storage
resource "aws_efs_file_system" "syslog_logs" {
  count            = var.enable_efs ? 1 : 0
  creation_token   = "syslog-receiver-logs"
  encrypted        = true
  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"
  
  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }
  
  lifecycle_policy {
    transition_to_primary_storage_class = "AFTER_1_ACCESS"
  }
  
  tags = {
    Name = "syslog-receiver-logs"
  }
}

# EFS Mount Targets (one per AZ)
resource "aws_efs_mount_target" "syslog_logs" {
  count           = var.enable_efs ? length(aws_subnet.private) : 0
  file_system_id  = aws_efs_file_system.syslog_logs[0].id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs[0].id]
}

# EFS Access Point
resource "aws_efs_access_point" "syslog_logs" {
  count          = var.enable_efs ? 1 : 0
  file_system_id = aws_efs_file_system.syslog_logs[0].id
  
  posix_user {
    gid = 1000
    uid = 1000
  }
  
  root_directory {
    path = "/logs"
    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "755"
    }
  }
  
  tags = {
    Name = "syslog-receiver-logs-ap"
  }
}

# EFS Backup Policy
resource "aws_efs_backup_policy" "syslog_logs" {
  count          = var.enable_efs ? 1 : 0
  file_system_id = aws_efs_file_system.syslog_logs[0].id
  
  backup_policy {
    status = "ENABLED"
  }
}

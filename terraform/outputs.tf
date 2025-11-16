output "nlb_dns_name" {
  description = "DNS name of the Network Load Balancer"
  value       = aws_lb.syslog_nlb.dns_name
}

output "nlb_zone_id" {
  description = "Zone ID of the Network Load Balancer"
  value       = aws_lb.syslog_nlb.zone_id
}

output "udp_endpoint" {
  description = "UDP endpoint for syslog"
  value       = "${aws_lb.syslog_nlb.dns_name}:514"
}

output "tls_endpoint" {
  description = "TLS endpoint for syslog"
  value       = "${aws_lb.syslog_nlb.dns_name}:6514"
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.syslog.name
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = aws_ecs_service.syslog_receiver.name
}

output "ecr_repository_url" {
  description = "URL of the ECR repository"
  value       = aws_ecr_repository.syslog_receiver.repository_url
}

output "efs_id" {
  description = "ID of the EFS filesystem for logs"
  value       = var.enable_efs ? aws_efs_file_system.syslog_logs[0].id : null
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.syslog_receiver.name
}

output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs."
  value       = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  description = "Security group ID for ALB/front door."
  value       = aws_security_group.alb.id
}

output "app_security_group_id" {
  description = "Security group ID for backend app/service."
  value       = aws_security_group.app.id
}

output "ecs_task_execution_role_arn" {
  description = "IAM role ARN for ECS task execution."
  value       = aws_iam_role.ecs_task_execution.arn
}

output "app_runtime_role_arn" {
  description = "IAM role ARN for app runtime (includes Bedrock invoke)."
  value       = aws_iam_role.app_runtime.arn
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch log group for app tasks."
  value       = aws_cloudwatch_log_group.app.name
}

output "load_balancer_dns_name" {
  description = "Public ALB DNS name."
  value       = aws_lb.app.dns_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.app.name
}

output "ecr_repository_url" {
  description = "ECR repository URL for backend image."
  value       = aws_ecr_repository.app.repository_url
}

output "scan_jobs_queue_url" {
  description = "SQS queue URL for scan jobs."
  value       = aws_sqs_queue.scan_jobs.id
}

output "db_endpoint" {
  description = "RDS endpoint hostname."
  value       = aws_db_instance.main.address
}

output "cost_savings_schedule_enabled" {
  description = "Whether automated cost-savings schedules are enabled."
  value       = var.enable_cost_savings_schedule
}

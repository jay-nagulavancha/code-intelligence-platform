variable "project_name" {
  description = "Project/application name."
  type        = string
  default     = "code-intelligence-platform"
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "us-west-2"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "public_subnet_count" {
  description = "Number of public subnets to create."
  type        = number
  default     = 2
}

variable "private_subnet_count" {
  description = "Number of private subnets to create."
  type        = number
  default     = 2
}

variable "app_port" {
  description = "Backend app listening port."
  type        = number
  default     = 8000
}

variable "bedrock_model_arn" {
  description = "Optional Bedrock model ARN for scoped invoke permissions. If empty, '*' is used."
  type        = string
  default     = ""
}

variable "app_image" {
  description = "Container image URI for backend app."
  type        = string
  default     = "public.ecr.aws/docker/library/python:3.11-slim"
}

variable "app_cpu" {
  description = "ECS task CPU units."
  type        = number
  default     = 512
}

variable "app_memory" {
  description = "ECS task memory in MB."
  type        = number
  default     = 1024
}

variable "app_desired_count" {
  description = "Desired ECS service task count."
  type        = number
  default     = 1
}

variable "app_health_check_path" {
  description = "HTTP health check path for ALB target group."
  type        = string
  default     = "/health"
}

variable "db_name" {
  description = "RDS database name."
  type        = string
  default     = "codeintel"
}

variable "db_username" {
  description = "RDS master username."
  type        = string
  default     = "codeintel_admin"
}

variable "db_password" {
  description = "RDS master password."
  type        = string
  sensitive   = true
  default     = "ChangeMe123!"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB."
  type        = number
  default     = 20
}

variable "enable_cost_savings_schedule" {
  description = "Enable scheduled scale down/stop for lower environments."
  type        = bool
  default     = true
}

variable "schedule_timezone" {
  description = "Timezone for scheduled cost-savings actions."
  type        = string
  default     = "America/Los_Angeles"
}

variable "workday_start_cron" {
  description = "Cron for start-of-day scale up/start action (EventBridge Scheduler format)."
  type        = string
  default     = "cron(0 8 ? * MON-FRI *)"
}

variable "workday_stop_cron" {
  description = "Cron for end-of-day scale down/stop action (EventBridge Scheduler format)."
  type        = string
  default     = "cron(0 20 ? * MON-FRI *)"
}

variable "ecs_workday_desired_count" {
  description = "Desired ECS task count during workday schedule."
  type        = number
  default     = 1
}


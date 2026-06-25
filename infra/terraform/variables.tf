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

variable "workspace_username" {
  description = "Linux username created on the CI workspace EC2 instance."
  type        = string
  default     = "ubuntu"
}

variable "workspace_project_name" {
  description = "Project label echoed by the workspace bootstrap script on completion."
  type        = string
  default     = "jay-ubuntu-workspace"
}

variable "workspace_vscode_password" {
  description = "Password for the code-server (VS Code web UI) instance on the CI workspace. Supply via terraform.tfvars (gitignored) or TF_VAR_workspace_vscode_password."
  type        = string
  sensitive   = false
  default     = "test"
}

variable "otasdp_poc_aws_profile" {
  description = "AWS CLI profile used to authenticate against the otasdp-poc AWS account (separate from the account holding the jay-ubuntu-workspace resources)."
  type        = string
  default     = "poc"
}

variable "otasdp_poc_vpc_cidr" {
  description = "CIDR block for the otasdp-poc VPC."
  type        = string
  default     = "10.60.0.0/16"
}

variable "otasdp_poc_availability_zone" {
  description = "Availability zone for the otasdp-poc subnet/instance."
  type        = string
  default     = "us-west-2a"
}

variable "otasdp_poc_instance_type" {
  description = "EC2 instance type for the otasdp-poc workspace."
  type        = string
  default     = "m5.large"
}

variable "otasdp_poc_ami_id" {
  description = "AMI ID for the otasdp-poc workspace instance."
  type        = string
  default     = "ami-0947c858572867ec7"
}

variable "otasdp_poc_root_volume_size" {
  description = "Root EBS volume size (GB) for the otasdp-poc workspace instance."
  type        = number
  default     = 100
}

variable "otasdp_poc_allowed_cidr_blocks" {
  description = "CIDR blocks allowed to reach the otasdp-poc workspace (SSH/HTTP/HTTPS/VS Code/FastAPI/Qdrant). Must be set explicitly before apply."
  type        = list(string)
}

variable "otasdp_poc_username" {
  description = "Linux username created on the otasdp-poc workspace EC2 instance."
  type        = string
  default     = "ubuntu"
}

variable "otasdp_poc_project_name" {
  description = "Project label echoed by the otasdp-poc workspace bootstrap script on completion."
  type        = string
  default     = "otasdp-poc"
}

variable "otasdp_poc_vscode_password" {
  description = "Password for the code-server (VS Code web UI) instance on the otasdp-poc workspace. Supply via terraform.tfvars (gitignored) or TF_VAR_otasdp_poc_vscode_password."
  type        = string
  sensitive   = true
}

variable "otasdp_poc_idle_cpu_threshold" {
  description = "CPU utilization percentage below which the otasdp-poc instance is considered idle."
  type        = number
  default     = 5
}

variable "otasdp_poc_idle_minutes" {
  description = "Minutes of sustained low CPU before the otasdp-poc instance is stopped. Must be a multiple of 5."
  type        = number
  default     = 30
}

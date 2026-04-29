# Terraform Infrastructure Project

This Terraform project bootstraps a deployable AWS stack for the Code Intelligence Platform.

## What it creates

- VPC with DNS enabled
- Public + private subnets across AZs
- Internet Gateway + NAT Gateway + route tables
- ALB + target group + HTTP listener
- ECS Fargate cluster, task definition, and service
- ECR repository for backend image
- SQS queue for scan jobs
- RDS PostgreSQL instance + subnet group
- EventBridge Scheduler-based cost controls:
  - ECS desired count set to `0` after-hours
  - ECS desired count restored on workday start
  - RDS stop/start schedule for non-prod savings
- Security groups for ALB, app tasks, and DB
- IAM roles/policies for ECS task execution and app runtime (including Bedrock invoke + SQS)
- CloudWatch log group for app logs

## Structure

- `versions.tf` - Terraform and provider version constraints
- `providers.tf` - AWS provider config
- `variables.tf` - input variables
- `main.tf` - core resources (network, compute, queue, database, IAM)
- `outputs.tf` - useful output values
- `terraform.tfvars.example` - starter variable values

## Quick start

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

## Notes

- Set a valid `app_image` in `terraform.tfvars` before `apply`.
- Change the example DB password before deploy.
- Bedrock permissions are scoped to a model ARN variable. Set `bedrock_model_arn` if you want strict scoping.
- Default ECS networking uses public subnets (`assign_public_ip = true`) for simplicity. Move tasks to private subnets + VPC endpoints/NAT-hardening for production.
- RDS auto-stop has AWS service constraints (for example, stopped DBs are auto-started by AWS after a maximum stop duration). The schedule keeps costs low but is not a permanent shutdown.

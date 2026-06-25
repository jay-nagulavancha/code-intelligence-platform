# Terraform Infrastructure Project

This Terraform project manages the AWS infrastructure backing the Code Intelligence Platform's CI workspace.

## What it manages

- `jay-ubuntu-workspace-ci-workspace` EC2 instance (Ubuntu, Docker, AWS CLI, Python 3.13, Java toolchain, SpotBugs/OWASP Dependency-Check, code-server)
- Its VPC, subnet, internet gateway, route table, and security group
- Its IAM role/instance profile (SSM, Bedrock, ECR auth, and a dedicated S3 bucket policy)
- Its S3 bucket (versioned, SSE-encrypted, public access blocked)
- Its SSH key pair

These resources already exist in AWS and were imported into Terraform state — `terraform plan` against them should show no changes besides default-tag metadata.

## Structure

- `versions.tf` - Terraform and provider version constraints
- `providers.tf` - AWS provider config
- `variables.tf` - input variables
- `workspace.tf` - the CI workspace EC2 instance and its supporting network/IAM/S3 resources
- `templates/workspace_bootstrap.sh.tftpl` - the instance's user-data bootstrap script
- `terraform.tfvars.example` - starter variable values

## Quick start

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# set workspace_vscode_password to the real code-server password
terraform init
terraform plan
```

## Notes

- `workspace_vscode_password` must match the live code-server password or `apply` will change it on the running instance.
- This project intentionally does not define a backend application stack (VPC/ALB/ECS/RDS) — only what already exists in the account is modeled here.

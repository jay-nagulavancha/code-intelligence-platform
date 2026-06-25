locals {
  workspace_name = "jay-ubuntu-workspace-ci-workspace"
}

resource "aws_vpc" "workspace" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${local.workspace_name}-vpc"
  }
}

resource "aws_internet_gateway" "workspace" {
  vpc_id = aws_vpc.workspace.id

  tags = {
    Name = "${local.workspace_name}-igw"
  }
}

resource "aws_subnet" "workspace" {
  vpc_id                  = aws_vpc.workspace.id
  cidr_block              = "10.42.1.0/24"
  availability_zone       = "us-west-2a"
  map_public_ip_on_launch = false

  tags = {
    Name = "${local.workspace_name}-subnet"
  }
}

resource "aws_route_table" "workspace" {
  vpc_id = aws_vpc.workspace.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.workspace.id
  }

  tags = {
    Name = "${local.workspace_name}-rt"
  }
}

resource "aws_route_table_association" "workspace" {
  subnet_id      = aws_subnet.workspace.id
  route_table_id = aws_route_table.workspace.id
}

resource "aws_security_group" "workspace" {
  name        = "${local.workspace_name}-sg"
  description = "Security group for code-intelligence-workspace"
  vpc_id      = aws_vpc.workspace.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["24.19.176.0/24"]
    description = "HTTP"
  }

  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["24.19.176.0/24"]
    description = "VS Code Server"
  }

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["24.19.176.0/24"]
    description = "FastAPI"
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["24.19.176.0/24"]
    description = "SSH"
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["24.19.49.17/32"]
  }

  ingress {
    from_port   = 6333
    to_port     = 6333
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Qdrant"
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["24.19.176.0/24"]
    description = "HTTPS"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.workspace_name}-sg"
  }
}

resource "aws_key_pair" "workspace" {
  key_name   = "${local.workspace_name}-key"
  public_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDB/iFQiQA3aVp0QaLxiXIvE0zyKMFoWk09lbf7kqw67B1gbM/zVkeVJdCJC1TSeMx7UPEi3ttj60XWLJaUQq/tdU6ny2ML5bwjEZO6bwdAX8q8wtqKx8BkOS0AMON8g6qMeg9xg+2VLlfY96hYekM5+KiHVw6SjjDOv929T7VFOZtEN3rhYiVkL6eD4Otjx5ALQxW8gGg0oAXODZaF/fFcRQhCB0QLUCRx7lihlQR0FniOYK9frPtnICEP08Vi9z9zADG3y8lymcVtUY6WcDiC+EGa1yHpYsJwEaMeFkY4KmQlq6H/nB3D9G4H1pEsXvviuHu/8NYt01I5VvWxcra3 jay-ubuntu-workspace-ci-workspace-key"

  lifecycle {
    ignore_changes = [public_key]
  }
}

data "aws_iam_policy_document" "workspace_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "workspace" {
  name               = "${local.workspace_name}-role"
  assume_role_policy = data.aws_iam_policy_document.workspace_assume_role.json

  tags = {
    Name = "${local.workspace_name}-role"
  }
}

resource "aws_iam_instance_profile" "workspace" {
  name = "${local.workspace_name}-profile"
  role = aws_iam_role.workspace.name
}

data "aws_iam_policy_document" "workspace_ecr_auth" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "workspace_ecr_auth" {
  name   = "${local.workspace_name}-ecr-auth"
  policy = data.aws_iam_policy_document.workspace_ecr_auth.json
}

resource "aws_iam_role_policy_attachment" "workspace_ecr_auth" {
  role       = aws_iam_role.workspace.name
  policy_arn = aws_iam_policy.workspace_ecr_auth.arn
}

data "aws_iam_policy_document" "workspace_s3" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.workspace.arn,
      "${aws_s3_bucket.workspace.arn}/*"
    ]
  }
}

resource "aws_iam_policy" "workspace_s3" {
  name   = "${local.workspace_name}-s3"
  policy = data.aws_iam_policy_document.workspace_s3.json
}

resource "aws_iam_role_policy_attachment" "workspace_s3" {
  role       = aws_iam_role.workspace.name
  policy_arn = aws_iam_policy.workspace_s3.arn
}

resource "aws_iam_role_policy_attachment" "workspace_ssm" {
  role       = aws_iam_role.workspace.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "workspace_bedrock" {
  role       = aws_iam_role.workspace.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
}

data "aws_iam_policy_document" "workspace_bedrock_invoke" {
  statement {
    sid = "AllowBedrockInvoke"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    resources = [
      "arn:aws:bedrock:us-west-2::foundation-model/*",
      "arn:aws:bedrock:us-west-2:626635446574:inference-profile/*"
    ]
  }

  statement {
    sid = "AllowBedrockModelDiscovery"
    actions = [
      "bedrock:ListFoundationModels",
      "bedrock:ListInferenceProfiles"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "workspace_bedrock_invoke" {
  name   = "BedrockInvokePolicy"
  role   = aws_iam_role.workspace.id
  policy = data.aws_iam_policy_document.workspace_bedrock_invoke.json
}

resource "aws_s3_bucket" "workspace" {
  bucket = "${local.workspace_name}-368af05b"

  tags = {
    Name    = local.workspace_name
    Purpose = "CodeIntelligencePlatform"
  }
}

resource "aws_s3_bucket_versioning" "workspace" {
  bucket = aws_s3_bucket.workspace.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "workspace" {
  bucket = aws_s3_bucket.workspace.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = false
  }
}

resource "aws_s3_bucket_public_access_block" "workspace" {
  bucket = aws_s3_bucket.workspace.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_instance" "workspace" {
  ami                         = "ami-0947c858572867ec7"
  instance_type               = "m5.large"
  subnet_id                   = aws_subnet.workspace.id
  vpc_security_group_ids      = [aws_security_group.workspace.id]
  key_name                    = aws_key_pair.workspace.key_name
  iam_instance_profile        = aws_iam_instance_profile.workspace.name
  associate_public_ip_address = true
  monitoring                  = true
  ebs_optimized               = false

  root_block_device {
    volume_type = "gp3"
    volume_size = 100
    iops        = 3000
    throughput  = 125
    encrypted   = true
    kms_key_id  = "arn:aws:kms:us-west-2:626635446574:key/07cff916-c167-4f6f-a181-4e40af400a2b"
  }

  metadata_options {
    http_tokens                 = "optional"
    http_put_response_hop_limit = 1
  }

  user_data = templatefile("${path.module}/templates/workspace_bootstrap.sh.tftpl", {
    username        = var.workspace_username
    vscode_password = var.workspace_vscode_password
    project_name    = var.workspace_project_name
  })

  tags = {
    Name    = local.workspace_name
    Purpose = "CodeIntelligencePlatform"
  }
}

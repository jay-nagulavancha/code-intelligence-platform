locals {
  otasdp_poc_prefix = "otasdp-poc"
}

resource "aws_vpc" "otasdp_poc" {
  provider = aws.otasdp_poc

  cidr_block           = var.otasdp_poc_vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${local.otasdp_poc_prefix}-vpc-main"
  }
}

resource "aws_internet_gateway" "otasdp_poc" {
  provider = aws.otasdp_poc

  vpc_id = aws_vpc.otasdp_poc.id

  tags = {
    Name = "${local.otasdp_poc_prefix}-igw-main"
  }
}

resource "aws_subnet" "otasdp_poc" {
  provider = aws.otasdp_poc

  vpc_id                  = aws_vpc.otasdp_poc.id
  cidr_block              = cidrsubnet(var.otasdp_poc_vpc_cidr, 8, 1)
  availability_zone       = var.otasdp_poc_availability_zone
  map_public_ip_on_launch = false

  tags = {
    Name = "${local.otasdp_poc_prefix}-subnet-main"
  }
}

resource "aws_route_table" "otasdp_poc" {
  provider = aws.otasdp_poc

  vpc_id = aws_vpc.otasdp_poc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.otasdp_poc.id
  }

  tags = {
    Name = "${local.otasdp_poc_prefix}-rtb-main"
  }
}

resource "aws_route_table_association" "otasdp_poc" {
  provider = aws.otasdp_poc

  subnet_id      = aws_subnet.otasdp_poc.id
  route_table_id = aws_route_table.otasdp_poc.id
}

resource "aws_default_security_group" "otasdp_poc" {
  provider = aws.otasdp_poc

  vpc_id = aws_vpc.otasdp_poc.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.otasdp_poc_allowed_cidr_blocks
    description = "HTTP"
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.otasdp_poc_allowed_cidr_blocks
    description = "HTTPS"
  }

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = var.otasdp_poc_allowed_cidr_blocks
    description = "FastAPI"
  }

  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = var.otasdp_poc_allowed_cidr_blocks
    description = "VS Code Server"
  }

  ingress {
    from_port   = 6333
    to_port     = 6333
    protocol    = "tcp"
    cidr_blocks = var.otasdp_poc_allowed_cidr_blocks
    description = "Qdrant"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.otasdp_poc_prefix}-sg-default"
  }
}

data "aws_iam_policy_document" "otasdp_poc_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "otasdp_poc" {
  provider = aws.otasdp_poc

  name               = "${local.otasdp_poc_prefix}-iam-role-workspace"
  assume_role_policy = data.aws_iam_policy_document.otasdp_poc_assume_role.json

  tags = {
    Name = "${local.otasdp_poc_prefix}-iam-role-workspace"
  }
}

resource "aws_iam_instance_profile" "otasdp_poc" {
  provider = aws.otasdp_poc_untagged

  name = "${local.otasdp_poc_prefix}-iam-profile-workspace"
  role = aws_iam_role.otasdp_poc.name
}

data "aws_iam_policy_document" "otasdp_poc_ecr_auth" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "otasdp_poc_ecr_auth" {
  provider = aws.otasdp_poc_untagged

  name   = "${local.otasdp_poc_prefix}-iam-policy-ecrauth"
  policy = data.aws_iam_policy_document.otasdp_poc_ecr_auth.json
}

resource "aws_iam_role_policy_attachment" "otasdp_poc_ecr_auth" {
  provider = aws.otasdp_poc

  role       = aws_iam_role.otasdp_poc.name
  policy_arn = aws_iam_policy.otasdp_poc_ecr_auth.arn
}

data "aws_iam_policy_document" "otasdp_poc_s3" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.otasdp_poc.arn,
      "${aws_s3_bucket.otasdp_poc.arn}/*"
    ]
  }
}

resource "aws_iam_policy" "otasdp_poc_s3" {
  provider = aws.otasdp_poc_untagged

  name   = "${local.otasdp_poc_prefix}-iam-policy-s3"
  policy = data.aws_iam_policy_document.otasdp_poc_s3.json
}

resource "aws_iam_role_policy_attachment" "otasdp_poc_s3" {
  provider = aws.otasdp_poc

  role       = aws_iam_role.otasdp_poc.name
  policy_arn = aws_iam_policy.otasdp_poc_s3.arn
}

data "aws_iam_policy_document" "otasdp_poc_ssm" {
  statement {
    actions = [
      "ssm:DescribeAssociation",
      "ssm:GetDeployablePatchSnapshotForInstance",
      "ssm:GetDocument",
      "ssm:DescribeDocument",
      "ssm:GetManifest",
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:ListAssociations",
      "ssm:ListInstanceAssociations",
      "ssm:PutInventory",
      "ssm:PutComplianceItems",
      "ssm:PutConfigurePackageResult",
      "ssm:UpdateAssociationStatus",
      "ssm:UpdateInstanceAssociationStatus",
      "ssm:UpdateInstanceInformation",
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
      "ec2messages:AcknowledgeMessage",
      "ec2messages:DeleteMessage",
      "ec2messages:FailMessage",
      "ec2messages:GetEndpoint",
      "ec2messages:GetMessages",
      "ec2messages:SendReply"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "otasdp_poc_ssm" {
  provider = aws.otasdp_poc

  name   = "SSMSessionManagerPolicy"
  role   = aws_iam_role.otasdp_poc.id
  policy = data.aws_iam_policy_document.otasdp_poc_ssm.json
}

data "aws_iam_policy_document" "otasdp_poc_bedrock_invoke" {
  statement {
    sid = "AllowBedrockInvoke"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:*:673725943782:inference-profile/*"
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

resource "aws_iam_role_policy" "otasdp_poc_bedrock_invoke" {
  provider = aws.otasdp_poc

  name   = "BedrockInvokePolicy"
  role   = aws_iam_role.otasdp_poc.id
  policy = data.aws_iam_policy_document.otasdp_poc_bedrock_invoke.json
}

resource "aws_iam_role_policy" "otasdp_poc_alarm_rearm" {
  provider = aws.otasdp_poc

  name = "AlarmReArmPolicy"
  role = aws_iam_role.otasdp_poc.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["cloudwatch:SetAlarmState"]
      Resource = aws_cloudwatch_metric_alarm.otasdp_poc_idle_stop.arn
    }]
  })
}

resource "random_id" "otasdp_poc_bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "otasdp_poc" {
  provider = aws.otasdp_poc

  bucket = "${local.otasdp_poc_prefix}-${random_id.otasdp_poc_bucket_suffix.hex}"

  tags = {
    Name = "${local.otasdp_poc_prefix}-s3-bucket"
  }
}

resource "aws_s3_bucket_versioning" "otasdp_poc" {
  provider = aws.otasdp_poc

  bucket = aws_s3_bucket.otasdp_poc.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "otasdp_poc" {
  provider = aws.otasdp_poc

  bucket = aws_s3_bucket.otasdp_poc.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = false
  }
}

resource "aws_s3_bucket_public_access_block" "otasdp_poc" {
  provider = aws.otasdp_poc

  bucket = aws_s3_bucket.otasdp_poc.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_instance" "otasdp_poc" {
  provider = aws.otasdp_poc

  ami                         = var.otasdp_poc_ami_id
  instance_type               = var.otasdp_poc_instance_type
  subnet_id                   = aws_subnet.otasdp_poc.id
  vpc_security_group_ids      = [aws_default_security_group.otasdp_poc.id]
  iam_instance_profile        = aws_iam_instance_profile.otasdp_poc.name
  associate_public_ip_address = true
  monitoring                  = true
  ebs_optimized               = false

  volume_tags = {
    Name        = "${local.otasdp_poc_prefix}-ebs-root"
    Environment = "poc"
    Project     = "otasdp"
    Owner       = "Jayavardhan.Nagulavancha@ttsystems.com"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.otasdp_poc_root_volume_size
    iops        = 3000
    throughput  = 125
    encrypted   = true
  }

  metadata_options {
    http_tokens                 = "optional"
    http_put_response_hop_limit = 1
  }

  user_data = templatefile("${path.module}/templates/workspace_bootstrap.sh.tftpl", {
    username        = var.otasdp_poc_username
    vscode_password = var.otasdp_poc_vscode_password
    project_name    = var.otasdp_poc_project_name
  })

  lifecycle {
    ignore_changes = [user_data]
  }

  tags = {
    Name = "${local.otasdp_poc_prefix}-ec2-workspace"
  }
}

resource "aws_cloudwatch_metric_alarm" "otasdp_poc_idle_stop" {
  provider = aws.otasdp_poc

  alarm_name          = "${local.otasdp_poc_prefix}-ec2-idle-stop"
  alarm_description   = "Stops ${aws_instance.otasdp_poc.id} after ${var.otasdp_poc_idle_minutes} minutes of CPU below ${var.otasdp_poc_idle_cpu_threshold}%."
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  comparison_operator = "LessThanThreshold"
  threshold           = var.otasdp_poc_idle_cpu_threshold
  period              = 300
  evaluation_periods  = ceil(var.otasdp_poc_idle_minutes / 5)
  # "breaching" ensures missing datapoints (instance stopped/no metrics) count as idle,
  # so the alarm stays in ALARM rather than bouncing to INSUFFICIENT_DATA when stopped.
  # The re-arm on restart is handled by the EventBridge rule + Lambda below.
  treat_missing_data  = "breaching"

  dimensions = {
    InstanceId = aws_instance.otasdp_poc.id
  }

  alarm_actions = ["arn:aws:automate:${var.aws_region}:ec2:stop"]

  tags = {
    Name = "${local.otasdp_poc_prefix}-ec2-idle-stop"
  }
}

# Re-arms the idle-stop alarm each time the instance is started so ec2:stop fires again.
# Without this, the alarm stays stuck in ALARM after a manual restart and never re-triggers.
data "aws_iam_policy_document" "otasdp_poc_lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "otasdp_poc_alarm_reset" {
  provider           = aws.otasdp_poc
  name               = "${local.otasdp_poc_prefix}-iam-role-alarm-reset"
  assume_role_policy = data.aws_iam_policy_document.otasdp_poc_lambda_assume_role.json

  tags = {
    Name = "${local.otasdp_poc_prefix}-iam-role-alarm-reset"
  }
}

resource "aws_iam_role_policy" "otasdp_poc_alarm_reset" {
  provider = aws.otasdp_poc
  name     = "AlarmResetPolicy"
  role     = aws_iam_role.otasdp_poc_alarm_reset.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["cloudwatch:SetAlarmState"]
        Resource = aws_cloudwatch_metric_alarm.otasdp_poc_idle_stop.arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_lambda_function" "otasdp_poc_alarm_reset" {
  provider      = aws.otasdp_poc
  function_name = "${local.otasdp_poc_prefix}-alarm-reset"
  role          = aws_iam_role.otasdp_poc_alarm_reset.arn
  runtime       = "python3.12"
  handler       = "index.handler"
  timeout       = 30

  environment {
    variables = {
      ALARM_NAME = aws_cloudwatch_metric_alarm.otasdp_poc_idle_stop.alarm_name
    }
  }

  filename         = data.archive_file.otasdp_poc_alarm_reset.output_path
  source_code_hash = data.archive_file.otasdp_poc_alarm_reset.output_base64sha256

  tags = {
    Name = "${local.otasdp_poc_prefix}-lambda-alarm-reset"
  }
}

data "archive_file" "otasdp_poc_alarm_reset" {
  type        = "zip"
  output_path = "${path.module}/templates/alarm_reset.zip"

  source {
    filename = "index.py"
    content  = <<-PYTHON
      import os, boto3
      def handler(event, context):
          cw = boto3.client("cloudwatch")
          cw.set_alarm_state(
              AlarmName=os.environ["ALARM_NAME"],
              StateValue="INSUFFICIENT_DATA",
              StateReason="Re-armed by Lambda on EC2 instance start",
          )
    PYTHON
  }
}

# NOTE: otasdp-poc account denies events:PutRule, so EventBridge auto-trigger is not available.
# To re-arm the idle-stop alarm after manually starting the instance, invoke the Lambda directly:
#   aws lambda invoke --function-name otasdp-poc-alarm-reset --profile poc --region us-west-2 /dev/null

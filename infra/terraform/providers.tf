provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

provider "aws" {
  alias   = "otasdp_poc"
  region  = var.aws_region
  profile = var.otasdp_poc_aws_profile

  default_tags {
    tags = {
      Environment = "poc"
      Project     = "otasdp"
      Owner       = "Jayavardhan.Nagulavancha@ttsystems.com"
    }
  }
}

# otasdp-poc account denies iam:TagPolicy/iam:TagInstanceProfile entirely (even at create time),
# so resources that hit those APIs must use a provider with no default_tags to avoid auto-tagging.
provider "aws" {
  alias   = "otasdp_poc_untagged"
  region  = var.aws_region
  profile = var.otasdp_poc_aws_profile
}

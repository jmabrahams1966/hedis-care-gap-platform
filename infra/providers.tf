terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Recommended: configure a remote backend once the AWS account exists, e.g.
  # backend "s3" {
  #   bucket         = "hedis-care-gap-tfstate"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "hedis-care-gap-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region
}

# ACM certificates for CloudFront must live in us-east-1 regardless of where
# everything else runs.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

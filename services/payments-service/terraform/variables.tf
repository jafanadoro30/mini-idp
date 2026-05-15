variable "service_name" {
  description = "Name of the service"
  type        = string
  default     = "payments-service"
}

variable "environment" {
  description = "Deployment environment (local, dev, staging, prod)"
  type        = string
  default     = "local"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "localstack_endpoint" {
  description = "LocalStack endpoint URL"
  type        = string
  default     = "http://localhost:4566"
}

output "bucket_name" {
  description = "S3 artifact bucket name"
  value       = aws_s3_bucket.artifacts.bucket
}

output "ssm_config_path" {
  description = "SSM parameter path for service config"
  value       = aws_ssm_parameter.config.name
}

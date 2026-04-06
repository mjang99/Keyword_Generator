variable "aws_region" {
  type        = string
  description = "AWS region for all managed resources."
  default     = "ap-northeast-2"
}

variable "project_name" {
  type        = string
  description = "Stable project prefix used in AWS resource names."
  default     = "keyword-generator"
}

variable "environment" {
  type        = string
  description = "Deployment environment name."
}

variable "artifact_bucket_force_destroy" {
  type        = bool
  description = "Whether the S3 artifact bucket can be force-destroyed."
  default     = false
}

variable "common_tags" {
  type        = map(string)
  description = "Tags applied to all resources."
  default = {
    Service = "keyword-generator"
  }
}

variable "hyper_tag_value" {
  type        = string
  description = "Value used for the mandatory hyper tag."
  default     = "true"
}

variable "mj_tag_value" {
  type        = string
  description = "Value used for the mandatory mj tag."
  default     = "true"
}

variable "policy_version" {
  type        = string
  description = "Runtime policy version to inject into Lambda env later."
  default     = "policy_v1"
}

variable "taxonomy_version" {
  type        = string
  description = "Runtime taxonomy version to inject into Lambda env later."
  default     = "tax_v2026_04_03"
}

variable "generator_version" {
  type        = string
  description = "Runtime generator version to inject into Lambda env later."
  default     = "gen_v3"
}

variable "generation_mode" {
  type        = string
  description = "Generation runtime mode injected into Lambda env."
  default     = "deterministic"
}

variable "bedrock_inference_profile_id" {
  type        = string
  description = "Optional Bedrock inference profile id."
  default     = null
  nullable    = true
}

variable "bedrock_model_id" {
  type        = string
  description = "Optional Bedrock model id."
  default     = null
  nullable    = true
}

variable "bedrock_max_tokens" {
  type        = number
  description = "Explicit Bedrock max token setting."
  default     = 3000
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention for managed Lambda log groups."
  default     = 14
}

variable "enable_zip_lambdas" {
  type        = bool
  description = "Whether to create the current zip-based Lambda functions and their IAM role."
  default     = false
}

variable "enable_http_api" {
  type        = bool
  description = "Whether to create the HTTP API Gateway routes for submit/get job."
  default     = false
}

variable "enable_cache_validity_schedule" {
  type        = bool
  description = "Whether to create the daily EventBridge schedule for the cache validity worker."
  default     = false
}

variable "zip_lambda_package_s3_bucket" {
  type        = string
  description = "S3 bucket holding the packaged zip Lambda artifact used by the current handlers."
  default     = null
  nullable    = true
}

variable "zip_lambda_package_s3_key" {
  type        = string
  description = "S3 key for the packaged zip Lambda artifact used by the current handlers."
  default     = null
  nullable    = true
}

variable "zip_lambda_package_s3_object_version" {
  type        = string
  description = "Optional S3 object version for the packaged zip Lambda artifact."
  default     = null
  nullable    = true
}

variable "lambda_architectures" {
  type        = list(string)
  description = "Architectures for managed zip Lambda functions."
  default     = ["arm64"]
}

variable "cache_validity_min_age_days" {
  type        = number
  description = "Minimum cache age before the cache validity worker checks entries."
  default     = 7
}

variable "cache_validity_schedule_expression" {
  type        = string
  description = "EventBridge schedule expression for the cache validity worker."
  default     = "rate(1 day)"
}

variable "http_api_stage_name" {
  type        = string
  description = "HTTP API stage name."
  default     = "$default"
}

variable "cognito_jwt_issuer" {
  type        = string
  description = "Optional JWT issuer URL for API Gateway authorizer."
  default     = null
  nullable    = true
}

variable "cognito_jwt_audience" {
  type        = list(string)
  description = "Optional JWT audience list for API Gateway authorizer."
  default     = []
}

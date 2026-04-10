output "artifact_bucket_name" {
  value       = aws_s3_bucket.artifacts.bucket
  description = "Artifact/cache S3 bucket."
}

output "runtime_table_name" {
  value       = aws_dynamodb_table.runtime.name
  description = "Job/UrlTask DynamoDB table."
}

output "queue_urls" {
  value = {
    collection   = aws_sqs_queue.main["collection"].url
    ocr          = aws_sqs_queue.main["ocr"].url
    generation   = aws_sqs_queue.main["generation"].url
    aggregation  = aws_sqs_queue.main["aggregation"].url
    notification = aws_sqs_queue.main["notification"].url
  }
  description = "Main SQS queue URLs."
}

output "dlq_urls" {
  value = {
    collection   = aws_sqs_queue.dlq["collection"].url
    ocr          = aws_sqs_queue.dlq["ocr"].url
    generation   = aws_sqs_queue.dlq["generation"].url
    aggregation  = aws_sqs_queue.dlq["aggregation"].url
    notification = aws_sqs_queue.dlq["notification"].url
  }
  description = "Dead-letter queue URLs."
}

output "lambda_env_reference" {
  value = merge({
    KEYWORD_GENERATOR_BUCKET                 = aws_s3_bucket.artifacts.bucket
    KEYWORD_GENERATOR_TABLE                  = aws_dynamodb_table.runtime.name
    KEYWORD_GENERATOR_COLLECTION_QUEUE_URL   = aws_sqs_queue.main["collection"].url
    KEYWORD_GENERATOR_OCR_QUEUE_URL          = aws_sqs_queue.main["ocr"].url
    KEYWORD_GENERATOR_GENERATION_QUEUE_URL   = aws_sqs_queue.main["generation"].url
    KEYWORD_GENERATOR_AGGREGATION_QUEUE_URL  = aws_sqs_queue.main["aggregation"].url
    KEYWORD_GENERATOR_NOTIFICATION_QUEUE_URL = aws_sqs_queue.main["notification"].url
    KEYWORD_GENERATOR_POLICY_VERSION         = var.policy_version
    KEYWORD_GENERATOR_TAXONOMY_VERSION       = var.taxonomy_version
    KEYWORD_GENERATOR_GENERATOR_VERSION      = var.generator_version
    KEYWORD_GENERATOR_GENERATION_MODE        = var.generation_mode
    BEDROCK_INFERENCE_PROFILE_ID             = var.bedrock_inference_profile_id
    BEDROCK_MODEL_ID                         = var.bedrock_model_id
    BEDROCK_MAX_TOKENS                       = tostring(var.bedrock_max_tokens)
    CACHE_VALIDITY_MIN_AGE_DAYS              = tostring(var.cache_validity_min_age_days)
  }, var.enable_collection_worker_image_lambda ? {
    KEYWORD_GENERATOR_COLLECTION_CRAWL4AI_FALLBACK_ENABLED = var.collection_worker_enable_crawl4ai_fallback ? "1" : "0"
    KEYWORD_GENERATOR_CRAWL4AI_WAIT_FOR_IMAGES             = var.collection_worker_crawl4ai_wait_for_images ? "1" : "0"
    KEYWORD_GENERATOR_CRAWL4AI_SIMULATE_USER               = var.collection_worker_crawl4ai_simulate_user ? "1" : "0"
    KEYWORD_GENERATOR_CRAWL4AI_REMOVE_OVERLAYS             = var.collection_worker_crawl4ai_remove_overlays ? "1" : "0"
    KEYWORD_GENERATOR_CRAWL4AI_MAGIC                       = var.collection_worker_crawl4ai_magic ? "1" : "0"
    KEYWORD_GENERATOR_CRAWL4AI_ENABLE_STEALTH              = var.collection_worker_crawl4ai_enable_stealth ? "1" : "0"
  } : {})
  description = "Environment values to inject into Lambda functions."
}

output "ecr_repository_urls" {
  value = {
    for name, repo in aws_ecr_repository.container_repo : name => repo.repository_url
  }
  description = "ECR repositories reserved for future container workers."
}

output "lambda_function_names" {
  value = {
    for name, fn in aws_lambda_function.current : name => fn.function_name
  }
  description = "Managed Lambda function names when enabled."
}

output "lambda_function_arns" {
  value = {
    for name, fn in aws_lambda_function.current : name => fn.arn
  }
  description = "Managed Lambda function ARNs when enabled."
}

output "http_api_invoke_url" {
  value       = try(aws_apigatewayv2_stage.http[0].invoke_url, null)
  description = "HTTP API invoke URL when enabled."
}

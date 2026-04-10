locals {
  zip_lambda_enabled = (
    var.enable_zip_lambdas &&
    var.zip_lambda_package_s3_bucket != null &&
    var.zip_lambda_package_s3_key != null
  )

  collection_worker_image_enabled = (
    var.enable_collection_worker_image_lambda &&
    var.collection_worker_image_uri != null
  )

  lambda_runtime_enabled = local.zip_lambda_enabled || local.collection_worker_image_enabled

  lambda_environment = {
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
    PYTHONIOENCODING                         = "utf-8"
    PYTHONUTF8                               = "1"
  }

  collection_worker_environment = merge(
    local.lambda_environment,
    {
      KEYWORD_GENERATOR_COLLECTION_CRAWL4AI_FALLBACK_ENABLED = var.collection_worker_enable_crawl4ai_fallback ? "1" : "0"
      KEYWORD_GENERATOR_CRAWL4AI_WAIT_FOR_IMAGES             = var.collection_worker_crawl4ai_wait_for_images ? "1" : "0"
      KEYWORD_GENERATOR_CRAWL4AI_SIMULATE_USER               = var.collection_worker_crawl4ai_simulate_user ? "1" : "0"
      KEYWORD_GENERATOR_CRAWL4AI_REMOVE_OVERLAYS             = var.collection_worker_crawl4ai_remove_overlays ? "1" : "0"
      KEYWORD_GENERATOR_CRAWL4AI_MAGIC                       = var.collection_worker_crawl4ai_magic ? "1" : "0"
      KEYWORD_GENERATOR_CRAWL4AI_ENABLE_STEALTH              = var.collection_worker_crawl4ai_enable_stealth ? "1" : "0"
    }
  )

  current_zip_functions = {
    submit_api = {
      function_name = "${local.name_prefix}-submit-api"
      description   = "Submit job HTTP handler."
      package_type  = "Zip"
      handler       = "src.handlers.api.submit_job_handler"
      memory_size   = 512
      timeout       = 30
      environment   = local.lambda_environment
    }
    get_job_api = {
      function_name = "${local.name_prefix}-get-job-api"
      description   = "Get job HTTP handler."
      package_type  = "Zip"
      handler       = "src.handlers.api.get_job_handler"
      memory_size   = 512
      timeout       = 30
      environment   = local.lambda_environment
    }
    aggregation_worker = {
      function_name = "${local.name_prefix}-aggregation-worker"
      description   = "Aggregation worker for combined exports and terminal job status."
      package_type  = "Zip"
      handler       = "src.handlers.workers.aggregation_worker_handler"
      memory_size   = 1024
      timeout       = 180
      environment   = local.lambda_environment
    }
    notification_worker = {
      function_name = "${local.name_prefix}-notification-worker"
      description   = "Notification worker for email/webhook delivery."
      package_type  = "Zip"
      handler       = "src.handlers.workers.notification_worker_handler"
      memory_size   = 512
      timeout       = 60
      environment   = local.lambda_environment
    }
    cache_validity_worker = {
      function_name = "${local.name_prefix}-cache-validity-worker"
      description   = "Scheduled cache validity sweeper."
      package_type  = "Zip"
      handler       = "src.handlers.cache_validity_worker.cache_validity_worker_handler"
      memory_size   = 1024
      timeout       = 300
      environment   = local.lambda_environment
    }
  }

  current_zip_functions_enabled = local.zip_lambda_enabled ? local.current_zip_functions : {}

  current_image_functions = {
    collection_worker = {
      function_name = "${local.name_prefix}-collection-worker"
      description   = "Collection worker for fetch, evidence build, and generation."
      package_type  = "Image"
      memory_size   = 3072
      timeout       = 900
      environment   = local.collection_worker_environment
    }
  }

  current_image_functions_enabled = local.collection_worker_image_enabled ? local.current_image_functions : {}

  managed_lambda_functions = merge(local.current_zip_functions_enabled, local.current_image_functions_enabled)
}

resource "aws_ecr_repository" "container_repo" {
  for_each = {
    collection = "${var.project_name}/collection-worker"
    ocr        = "${var.project_name}/ocr-worker"
  }

  name                 = each.value
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
}

resource "aws_iam_role" "lambda_exec" {
  count = local.lambda_runtime_enabled ? 1 : 0

  name = "${local.name_prefix}-lambda-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  count = local.lambda_runtime_enabled ? 1 : 0

  role       = aws_iam_role.lambda_exec[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_runtime" {
  count = local.lambda_runtime_enabled ? 1 : 0

  name = "${local.name_prefix}-lambda-runtime"
  role = aws_iam_role.lambda_exec[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:AbortMultipartUpload",
          "s3:DeleteObject",
          "s3:GetObject",
          "s3:HeadObject",
          "s3:ListBucket",
          "s3:PutObject"
        ]
        Resource = [
          aws_s3_bucket.artifacts.arn,
          "${aws_s3_bucket.artifacts.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:BatchWriteItem",
          "dynamodb:DeleteItem",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.runtime.arn
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ChangeMessageVisibility",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl",
          "sqs:ReceiveMessage",
          "sqs:SendMessage"
        ]
        Resource = concat(
          [for queue in aws_sqs_queue.main : queue.arn],
          [for queue in aws_sqs_queue.dlq : queue.arn]
        )
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.managed_lambda_functions

  name              = "/aws/lambda/${each.value.function_name}"
  retention_in_days = var.log_retention_days

  tags = local.tags
}

resource "aws_lambda_function" "current" {
  for_each = local.managed_lambda_functions

  function_name = each.value.function_name
  description   = each.value.description
  role          = aws_iam_role.lambda_exec[0].arn
  package_type  = each.value.package_type
  runtime       = each.value.package_type == "Zip" ? "python3.13" : null
  architectures = each.value.package_type == "Image" ? var.collection_worker_image_architectures : var.lambda_architectures
  handler       = each.value.package_type == "Zip" ? each.value.handler : null
  memory_size   = each.value.memory_size
  timeout       = each.value.timeout
  image_uri     = each.value.package_type == "Image" ? var.collection_worker_image_uri : null

  s3_bucket         = each.value.package_type == "Zip" ? var.zip_lambda_package_s3_bucket : null
  s3_key            = each.value.package_type == "Zip" ? var.zip_lambda_package_s3_key : null
  s3_object_version = each.value.package_type == "Zip" ? var.zip_lambda_package_s3_object_version : null

  environment {
    variables = {
      for key, value in each.value.environment : key => value
      if value != null
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_runtime,
    aws_cloudwatch_log_group.lambda,
  ]

  tags = local.tags
}

resource "aws_lambda_event_source_mapping" "collection_queue" {
  count = local.lambda_runtime_enabled ? 1 : 0

  event_source_arn = aws_sqs_queue.main["collection"].arn
  function_name    = aws_lambda_function.current["collection_worker"].arn
  batch_size       = 1
}

resource "aws_lambda_event_source_mapping" "aggregation_queue" {
  count = local.zip_lambda_enabled ? 1 : 0

  event_source_arn = aws_sqs_queue.main["aggregation"].arn
  function_name    = aws_lambda_function.current["aggregation_worker"].arn
  batch_size       = 1
}

resource "aws_lambda_event_source_mapping" "notification_queue" {
  count = local.zip_lambda_enabled ? 1 : 0

  event_source_arn = aws_sqs_queue.main["notification"].arn
  function_name    = aws_lambda_function.current["notification_worker"].arn
  batch_size       = 1
}

resource "aws_cloudwatch_event_rule" "cache_validity" {
  count = local.zip_lambda_enabled && var.enable_cache_validity_schedule ? 1 : 0

  name                = "${local.name_prefix}-cache-validity"
  description         = "Daily cache validity sweep for stale cache entries."
  schedule_expression = var.cache_validity_schedule_expression

  tags = local.tags
}

resource "aws_cloudwatch_event_target" "cache_validity" {
  count = local.zip_lambda_enabled && var.enable_cache_validity_schedule ? 1 : 0

  rule      = aws_cloudwatch_event_rule.cache_validity[0].name
  target_id = "cache-validity-worker"
  arn       = aws_lambda_function.current["cache_validity_worker"].arn
}

resource "aws_lambda_permission" "allow_eventbridge_cache_validity" {
  count = local.zip_lambda_enabled && var.enable_cache_validity_schedule ? 1 : 0

  statement_id  = "AllowExecutionFromEventBridgeCacheValidity"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.current["cache_validity_worker"].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cache_validity[0].arn
}

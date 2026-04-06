locals {
  zip_lambda_enabled = (
    var.enable_zip_lambdas &&
    var.zip_lambda_package_s3_bucket != null &&
    var.zip_lambda_package_s3_key != null
  )

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
  }

  current_zip_functions = {
    submit_api = {
      function_name = "${local.name_prefix}-submit-api"
      description   = "Submit job HTTP handler."
      handler       = "src.handlers.api.submit_job_handler"
      memory_size   = 512
      timeout       = 30
    }
    get_job_api = {
      function_name = "${local.name_prefix}-get-job-api"
      description   = "Get job HTTP handler."
      handler       = "src.handlers.api.get_job_handler"
      memory_size   = 512
      timeout       = 30
    }
    collection_worker = {
      function_name = "${local.name_prefix}-collection-worker"
      description   = "Collection worker for fetch, evidence build, and generation."
      handler       = "src.handlers.workers.collection_worker_handler"
      memory_size   = 2048
      timeout       = 900
    }
    aggregation_worker = {
      function_name = "${local.name_prefix}-aggregation-worker"
      description   = "Aggregation worker for combined exports and terminal job status."
      handler       = "src.handlers.workers.aggregation_worker_handler"
      memory_size   = 1024
      timeout       = 180
    }
    notification_worker = {
      function_name = "${local.name_prefix}-notification-worker"
      description   = "Notification worker for email/webhook delivery."
      handler       = "src.handlers.workers.notification_worker_handler"
      memory_size   = 512
      timeout       = 60
    }
    cache_validity_worker = {
      function_name = "${local.name_prefix}-cache-validity-worker"
      description   = "Scheduled cache validity sweeper."
      handler       = "src.handlers.cache_validity_worker.cache_validity_worker_handler"
      memory_size   = 1024
      timeout       = 300
    }
  }

  current_zip_functions_enabled = local.zip_lambda_enabled ? local.current_zip_functions : {}
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
  count = local.zip_lambda_enabled ? 1 : 0

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
  count = local.zip_lambda_enabled ? 1 : 0

  role       = aws_iam_role.lambda_exec[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_runtime" {
  count = local.zip_lambda_enabled ? 1 : 0

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
  for_each = local.current_zip_functions_enabled

  name              = "/aws/lambda/${each.value.function_name}"
  retention_in_days = var.log_retention_days

  tags = local.tags
}

resource "aws_lambda_function" "current_zip" {
  for_each = local.current_zip_functions_enabled

  function_name = each.value.function_name
  description   = each.value.description
  role          = aws_iam_role.lambda_exec[0].arn
  runtime       = "python3.13"
  architectures = var.lambda_architectures
  handler       = each.value.handler
  memory_size   = each.value.memory_size
  timeout       = each.value.timeout

  s3_bucket         = var.zip_lambda_package_s3_bucket
  s3_key            = var.zip_lambda_package_s3_key
  s3_object_version = var.zip_lambda_package_s3_object_version

  environment {
    variables = {
      for key, value in local.lambda_environment : key => value
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
  count = local.zip_lambda_enabled ? 1 : 0

  event_source_arn = aws_sqs_queue.main["collection"].arn
  function_name    = aws_lambda_function.current_zip["collection_worker"].arn
  batch_size       = 1
}

resource "aws_lambda_event_source_mapping" "aggregation_queue" {
  count = local.zip_lambda_enabled ? 1 : 0

  event_source_arn = aws_sqs_queue.main["aggregation"].arn
  function_name    = aws_lambda_function.current_zip["aggregation_worker"].arn
  batch_size       = 1
}

resource "aws_lambda_event_source_mapping" "notification_queue" {
  count = local.zip_lambda_enabled ? 1 : 0

  event_source_arn = aws_sqs_queue.main["notification"].arn
  function_name    = aws_lambda_function.current_zip["notification_worker"].arn
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
  arn       = aws_lambda_function.current_zip["cache_validity_worker"].arn
}

resource "aws_lambda_permission" "allow_eventbridge_cache_validity" {
  count = local.zip_lambda_enabled && var.enable_cache_validity_schedule ? 1 : 0

  statement_id  = "AllowExecutionFromEventBridgeCacheValidity"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.current_zip["cache_validity_worker"].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cache_validity[0].arn
}

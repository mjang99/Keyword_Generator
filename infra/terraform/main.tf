locals {
  name_prefix = "${var.project_name}-${var.environment}"
  tags = merge(
    var.common_tags,
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      hyper       = var.hyper_tag_value
      mj          = var.mj_tag_value
    }
  )

  queues = {
    collection = {
      visibility_timeout_seconds = 1080
      max_receive_count          = 3
    }
    ocr = {
      visibility_timeout_seconds = 720
      max_receive_count          = 2
    }
    generation = {
      visibility_timeout_seconds = 540
      max_receive_count          = 2
    }
    aggregation = {
      visibility_timeout_seconds = 360
      max_receive_count          = 3
    }
    notification = {
      visibility_timeout_seconds = 180
      max_receive_count          = 3
    }
  }
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = "${local.name_prefix}-artifacts"
  force_destroy = var.artifact_bucket_force_destroy

  tags = local.tags
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "cache_expiry" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "cache-30day-expiry"
    status = "Enabled"

    filter {
      prefix = "cache/"
    }

    expiration {
      days = 30
    }
  }
}

resource "aws_dynamodb_table" "runtime" {
  name         = "${local.name_prefix}-runtime"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = local.tags
}

resource "aws_sqs_queue" "dlq" {
  for_each = local.queues

  name = "${local.name_prefix}-${each.key}-dlq"

  message_retention_seconds = 1209600
  tags                      = local.tags
}

resource "aws_sqs_queue" "main" {
  for_each = local.queues

  name                       = "${local.name_prefix}-${each.key}"
  visibility_timeout_seconds = each.value.visibility_timeout_seconds
  message_retention_seconds  = 345600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = each.value.max_receive_count
  })

  tags = local.tags
}

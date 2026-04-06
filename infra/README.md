# Infra Baseline

This directory is the AWS resource-management baseline for the URL Product Keyword Generator.

Current scope:

- resource inventory and naming rules
- Terraform scaffold for shared stateful resources
- Terraform-managed compute/API baseline behind feature flags
- environment variable mapping for Lambda/runtime wiring

Still out of scope:

- CloudWatch alarms and dashboards
- SES/webhook secret provisioning
- the future containerized OCR/runtime split described in the design doc

## Managed Resources

The Terraform scaffold under `infra/terraform/` manages:

- one S3 bucket for artifacts and cache
- one DynamoDB table for `Job` / `UrlTask`
- five main SQS queues
- five DLQs
- two ECR repositories reserved for the future collection/OCR container workers
- one shared IAM execution role for the current zip Lambda baseline when enabled
- six current zip Lambda functions when enabled
- one HTTP API for `POST /jobs` and `GET /jobs/{job_id}` when enabled
- one EventBridge schedule for cache validity sweeps when enabled

Every scaffold-managed resource is tagged with:

- `Service=keyword-generator` unless overridden in `common_tags`
- `Environment=<env>`
- `ManagedBy=terraform`
- `hyper=<hyper_tag_value>`
- `mj=<mj_tag_value>`

The current deployable baseline matches the code that exists today:

- `submit_api`
- `get_job_api`
- `collection_worker`
- `aggregation_worker`
- `notification_worker`
- `cache_validity_worker`

The design doc still describes a future split with dedicated OCR and generation workers. Those container images are reserved with ECR repositories now, but the Terraform baseline does not create those Lambda functions yet because the current Python handlers do not expose them as standalone entrypoints.

## Runtime Env Mapping

The current Python runtime bootstrap reads these environment variables:

- `KEYWORD_GENERATOR_BUCKET`
- `KEYWORD_GENERATOR_TABLE`
- `KEYWORD_GENERATOR_COLLECTION_QUEUE_URL`
- `KEYWORD_GENERATOR_AGGREGATION_QUEUE_URL`
- `KEYWORD_GENERATOR_NOTIFICATION_QUEUE_URL`
- `KEYWORD_GENERATOR_POLICY_VERSION`
- `KEYWORD_GENERATOR_TAXONOMY_VERSION`
- `KEYWORD_GENERATOR_GENERATOR_VERSION`
- `KEYWORD_GENERATOR_GENERATION_MODE`
- `BEDROCK_INFERENCE_PROFILE_ID` or `BEDROCK_MODEL_ID`
- `BEDROCK_MAX_TOKENS`
- `CACHE_VALIDITY_MIN_AGE_DAYS`

The runtime ignores the OCR and generation queue URLs today, but Terraform still exports them because the design contract and future worker split already reserve those stages.

## Feature Flags

The baseline is intentionally progressive:

- `enable_zip_lambdas=true` creates the current six Lambda functions and IAM role
- `enable_http_api=true` creates the HTTP API on top of the submit/get Lambda pair
- `enable_cache_validity_schedule=true` attaches the daily EventBridge trigger

Zip Lambda creation also requires:

- `zip_lambda_package_s3_bucket`
- `zip_lambda_package_s3_key`
- optionally `zip_lambda_package_s3_object_version`

For reliable rollouts, prefer one of these:

- upload each release to a new S3 key
- or keep the same key but set `zip_lambda_package_s3_object_version`

## Apply Order

1. provision shared resources in `infra/terraform/`
2. upload the current Lambda zip package to S3
3. re-apply with `enable_zip_lambdas=true`
4. optionally enable `enable_http_api=true`
5. enable `KEYWORD_GENERATOR_GENERATION_MODE=bedrock` only after Bedrock smoke checks pass

If you want only the persistent resources first, leave all feature flags disabled.

Useful local commands:

- package current Lambda code: `powershell -ExecutionPolicy Bypass -File .\scripts\package_lambda.ps1`
- upload a built zip to S3: `.\.venv-dev\Scripts\python.exe scripts\upload_lambda_package.py --file <zip> --bucket <bucket> --key <key> --region ap-northeast-2`

## Naming Rule

Resource names follow:

- `${project_name}-${environment}-${resource}`

Examples:

- `keyword-generator-dev-artifacts`
- `keyword-generator-dev-runtime`
- `keyword-generator-dev-collection`
- `keyword-generator-dev-collection-dlq`
- `keyword-generator-dev-submit-api`
- `keyword-generator-dev-api`

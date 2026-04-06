# AWS Resource Inventory

This document is the operator-facing inventory for the first deployable AWS footprint.

## Shared Resources

| Resource | Count | Naming rule | Managed now |
| --- | --- | --- | --- |
| S3 artifact bucket | 1 | `${project}-${env}-artifacts` | yes |
| DynamoDB runtime table | 1 | `${project}-${env}-runtime` | yes |
| Main SQS queues | 5 | `${project}-${env}-{stage}` | yes |
| SQS DLQs | 5 | `${project}-${env}-{stage}-dlq` | yes |
| Lambda functions | 6 | `${project}-${env}-{function}` | conditional |
| Lambda container image repos | 2 | `${project}/{function}` in ECR | yes |
| API Gateway | 1 | `${project}-${env}-api` | conditional |
| CloudWatch alarms | many | `${project}-${env}-{metric}` | no |
| EventBridge cache sweep schedule | 1 | `${project}-${env}-cache-validity` | conditional |
| SES/webhook secrets | as needed | `${project}/${env}/{secret}` | no |

## Mandatory Tags

All Terraform-managed resources in the current scaffold carry these tags:

| Tag | Default value |
| --- | --- |
| `Service` | `keyword-generator` |
| `Environment` | `${env}` |
| `ManagedBy` | `terraform` |
| `hyper` | `true` |
| `mj` | `true` |

## Queue Set

| Queue | Producer | Consumer | Visibility timeout | DLQ max receive |
| --- | --- | --- | --- | --- |
| `collection` | submit | collection worker | 1080s | 3 |
| `ocr` | collection worker | future OCR worker | 720s | 2 |
| `generation` | collection/OCR worker | future generation worker | 540s | 2 |
| `aggregation` | submit/collection/generation | aggregator | 360s | 3 |
| `notification` | aggregator | notification sender | 180s | 3 |

## Current Deployable Lambda Baseline

The current codebase exposes these direct Lambda entrypoints:

| Function | Handler | Trigger |
| --- | --- | --- |
| `submit-api` | `src.handlers.api.submit_job_handler` | HTTP API `POST /jobs` |
| `get-job-api` | `src.handlers.api.get_job_handler` | HTTP API `GET /jobs/{job_id}` |
| `collection-worker` | `src.handlers.workers.collection_worker_handler` | `collection` queue |
| `aggregation-worker` | `src.handlers.workers.aggregation_worker_handler` | `aggregation` queue |
| `notification-worker` | `src.handlers.workers.notification_worker_handler` | `notification` queue |
| `cache-validity-worker` | `src.handlers.cache_validity_worker.cache_validity_worker_handler` | EventBridge schedule |

This is the deployable baseline Terraform now supports. The separate OCR and generation workers remain part of the future target architecture, so the `ocr` and `generation` queues are provisioned now but not yet mapped to Lambda functions.

## Lambda Env Contract

These values must be injected into the deployed Lambda functions:

| Env var | Purpose |
| --- | --- |
| `KEYWORD_GENERATOR_BUCKET` | artifact/cache bucket |
| `KEYWORD_GENERATOR_TABLE` | job/url-task DynamoDB table |
| `KEYWORD_GENERATOR_COLLECTION_QUEUE_URL` | queue URL for collection stage |
| `KEYWORD_GENERATOR_OCR_QUEUE_URL` | queue URL for OCR stage |
| `KEYWORD_GENERATOR_GENERATION_QUEUE_URL` | queue URL for generation stage |
| `KEYWORD_GENERATOR_AGGREGATION_QUEUE_URL` | queue URL for aggregation stage |
| `KEYWORD_GENERATOR_NOTIFICATION_QUEUE_URL` | queue URL for notification stage |
| `KEYWORD_GENERATOR_POLICY_VERSION` | runtime policy version |
| `KEYWORD_GENERATOR_TAXONOMY_VERSION` | taxonomy bundle version |
| `KEYWORD_GENERATOR_GENERATOR_VERSION` | generator logic version |
| `KEYWORD_GENERATOR_GENERATION_MODE` | `deterministic` or `bedrock` |
| `BEDROCK_INFERENCE_PROFILE_ID` or `BEDROCK_MODEL_ID` | Bedrock target |
| `BEDROCK_MAX_TOKENS` | explicit Bedrock token cap |
| `CACHE_VALIDITY_MIN_AGE_DAYS` | age gate for scheduled cache validation sweep |

## Deployment Split

Terraform scaffold under `infra/terraform/` now manages:

- shared persistent resources
- current zip Lambda baseline when enabled
- HTTP API when enabled
- ECR repos for the future container workers
- EventBridge cache sweep schedule when enabled

A later infra pass should add:

- CloudWatch alarms and dashboards
- SES and Secrets Manager resources
- the future OCR/generation Lambda split that consumes the already-created `ocr` and `generation` queues

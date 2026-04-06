# Bedrock Manual Check

## Purpose

Use this when you want to verify Bedrock access manually without wiring a runtime client into the service yet.

Current workspace status:

- There is no tracked runtime Bedrock client under `src/` yet.
- Manual ping script exists at [tests/check_bedrock_access.py](/c:/Users/NHN/Repo/Keyword_Generator/tests/check_bedrock_access.py).
- The script uses `ap-northeast-2` by default.
- The script tries APAC cross-region Claude 3.5 Sonnet profiles by default unless you override them with environment variables.

## 1. Install Test Dependencies

If you are using the local target install approach already prepared in this workspace:

```powershell
python -m pip install --target .\.deps -r requirements-dev.txt
```

If you prefer your own venv, install the same packages into that environment instead.

## 2. Set AWS Auth

If your credentials are already stored in `C:\Users\NHN\.aws\credentials` and `C:\Users\NHN\.aws\config`, you do not need to export access keys manually.

Default behavior:

- If the AWS SDK can resolve a default profile from `~/.aws`, the script will use it automatically.
- If you have multiple profiles, set only `AWS_PROFILE` and leave the secret values in `~/.aws`.

Your current case:

```powershell
$env:AWS_DEFAULT_REGION = "ap-northeast-2"
```

Because your `default` profile is already correct, `AWS_PROFILE` is not needed.

Only set `AWS_PROFILE` when you want to override the default profile:

```powershell
$env:AWS_PROFILE = "148761639846"
```

Only use raw environment variables when you intentionally want to bypass `~/.aws` profile resolution:

```powershell
$env:AWS_ACCESS_KEY_ID = "..."
$env:AWS_SECRET_ACCESS_KEY = "..."
$env:AWS_SESSION_TOKEN = "..."  # if needed
```

Always set the region:

```powershell
$env:AWS_DEFAULT_REGION = "ap-northeast-2"
```

## 3. Optional Model Override

The script already has working defaults for APAC cross-region inference. Only override if your account uses a different profile or model.

Inference profile override:

```powershell
$env:BEDROCK_INFERENCE_PROFILE_ID = "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"
```

Direct model override:

```powershell
$env:BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
```

Prefer the inference profile when available.

## 4. Run The Manual Check

If you are using the local `.deps` directory:

```powershell
$env:AWS_DEFAULT_REGION = "ap-northeast-2"
$env:PYTHONPATH = ".\.deps"
python tests\check_bedrock_access.py
```

Expected success output includes:

```text
Bedrock access OK
```

## 5. What The Script Prints

- `region`
- `model_candidates`
- `model_source`
- `max_tokens`
- `trying_model_id`
- `resolved_model_id` on success

For the ping script only, `max_tokens=16`.

That is intentionally small because this is a connectivity check, not a generation workload.

## 6. Generation-Time Guidance

For the real keyword generation path:

- keep region at `ap-northeast-2`
- prefer cross-region inference profile IDs when throughput matters
- set `max_tokens` explicitly on every Bedrock call
- recommended generation range for 100-keyword output: `2000` to `4000`

Do not leave `max_tokens` unset. That can reserve `64000` tokens and crush concurrency.

## 7. Failure Guide

`ValidationException`

- the model or inference profile ID is invalid for your account or region
- try setting `BEDROCK_INFERENCE_PROFILE_ID` explicitly

`AccessDeniedException`

- your IAM principal does not have Bedrock invoke permissions
- confirm access to both the inference profile and underlying model resources

`ThrottlingException`

- switch to a Geo/APAC cross-region inference profile
- reduce concurrency
- keep `max_tokens` explicit and small enough for the workload

`Missing Python dependency`

- install dependencies with `requirements-dev.txt`
- or run from your own prepared venv

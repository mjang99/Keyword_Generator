locals {
  jwt_authorizer_enabled = (
    var.enable_http_api &&
    local.zip_lambda_enabled &&
    var.cognito_jwt_issuer != null &&
    length(var.cognito_jwt_audience) > 0
  )

  http_api_enabled = var.enable_http_api && local.zip_lambda_enabled
}

resource "aws_apigatewayv2_api" "http" {
  count = local.http_api_enabled ? 1 : 0

  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"

  tags = local.tags
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  count = local.jwt_authorizer_enabled ? 1 : 0

  api_id          = aws_apigatewayv2_api.http[0].id
  authorizer_type = "JWT"
  name            = "${local.name_prefix}-jwt"

  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer   = var.cognito_jwt_issuer
    audience = var.cognito_jwt_audience
  }
}

resource "aws_apigatewayv2_integration" "submit" {
  count = local.http_api_enabled ? 1 : 0

  api_id                 = aws_apigatewayv2_api.http[0].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.current["submit_api"].invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "get_job" {
  count = local.http_api_enabled ? 1 : 0

  api_id                 = aws_apigatewayv2_api.http[0].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.current["get_job_api"].invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "submit" {
  count = local.http_api_enabled ? 1 : 0

  api_id    = aws_apigatewayv2_api.http[0].id
  route_key = "POST /jobs"
  target    = "integrations/${aws_apigatewayv2_integration.submit[0].id}"

  authorization_type = local.jwt_authorizer_enabled ? "JWT" : "NONE"
  authorizer_id      = local.jwt_authorizer_enabled ? aws_apigatewayv2_authorizer.jwt[0].id : null
}

resource "aws_apigatewayv2_route" "get_job" {
  count = local.http_api_enabled ? 1 : 0

  api_id    = aws_apigatewayv2_api.http[0].id
  route_key = "GET /jobs/{job_id}"
  target    = "integrations/${aws_apigatewayv2_integration.get_job[0].id}"

  authorization_type = local.jwt_authorizer_enabled ? "JWT" : "NONE"
  authorizer_id      = local.jwt_authorizer_enabled ? aws_apigatewayv2_authorizer.jwt[0].id : null
}

resource "aws_apigatewayv2_stage" "http" {
  count = local.http_api_enabled ? 1 : 0

  api_id      = aws_apigatewayv2_api.http[0].id
  name        = var.http_api_stage_name
  auto_deploy = true

  default_route_settings {
    detailed_metrics_enabled = true
    throttling_burst_limit   = 100
    throttling_rate_limit    = 50
  }

  tags = local.tags
}

resource "aws_lambda_permission" "allow_http_api_submit" {
  count = local.http_api_enabled ? 1 : 0

  statement_id  = "AllowExecutionFromHttpApiSubmit"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.current["submit_api"].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http[0].execution_arn}/*/*"
}

resource "aws_lambda_permission" "allow_http_api_get_job" {
  count = local.http_api_enabled ? 1 : 0

  statement_id  = "AllowExecutionFromHttpApiGetJob"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.current["get_job_api"].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http[0].execution_arn}/*/*"
}

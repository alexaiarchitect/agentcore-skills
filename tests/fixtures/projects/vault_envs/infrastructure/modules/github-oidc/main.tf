data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.existing_oidc_provider_arn == "" ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
  tags            = var.tags
}

locals {
  provider_arn = var.existing_oidc_provider_arn != "" ? var.existing_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
  # Repositories with immutable OIDC subjects issue "repo:<org>@<org id>/<repo>@<repo id>".
  subject_prefix = var.subject_prefix != "" ? var.subject_prefix : "repo:${var.github_organization}/${var.github_repository}"
}

resource "aws_iam_role" "production_deploy" {
  name                 = "${var.name}-github-production"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "${local.subject_prefix}:environment:production"
        }
      }
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "production_deploy" {
  name = "${var.name}-production-deploy"
  role = aws_iam_role.production_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ManageVaultInfrastructure"
        Effect = "Allow"
        Action = [
          "acm:*",
          "apigateway:*",
          "budgets:*",
          "cloudwatch:*",
          "cognito-idp:*",
          "dynamodb:*",
          "lambda:*",
          "logs:*",
          "s3:*",
          "secretsmanager:*",
          "sns:*",
          "sqs:*",
        ]
        Resource = "*"
      },
      {
        Sid      = "ManageVaultRoles"
        Effect   = "Allow"
        Action   = ["iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:TagRole", "iam:UntagRole", "iam:UpdateAssumeRolePolicy", "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:PassRole"]
        Resource = "arn:aws:iam::*:role/${var.name}-*"
      },
      {
        Sid      = "ManageGithubOidcProvider"
        Effect   = "Allow"
        Action   = ["iam:GetOpenIDConnectProvider", "iam:CreateOpenIDConnectProvider", "iam:DeleteOpenIDConnectProvider", "iam:TagOpenIDConnectProvider", "iam:UntagOpenIDConnectProvider", "iam:UpdateOpenIDConnectProviderThumbprint", "iam:AddClientIDToOpenIDConnectProvider"]
        Resource = "arn:aws:iam::*:oidc-provider/token.actions.githubusercontent.com"
      },
      {
        Sid      = "ReadCallerIdentity"
        Effect   = "Allow"
        Action   = ["sts:GetCallerIdentity"]
        Resource = "*"
      },
    ]
  })
}

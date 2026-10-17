# Cognito recipes

## `cognito-inbound`: users and agents calling the gateway

Nothing is created in AgentCore. The gateway's authorizer gets:

```hcl
authorizer_type = "CUSTOM_JWT"
authorizer_configuration {
  custom_jwt_authorizer {
    discovery_url   = "${module.identity.issuer}/.well-known/openid-configuration"
    allowed_clients = module.identity.authorized_client_ids
    allowed_scopes  = ["https://mcp.example.test/mcp/records.read"] # optional
  }
}
```

The issuer form works when the Cognito module exports
`https://${aws_cognito_user_pool.x.endpoint}`; otherwise
`https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/openid-configuration`.
Include both the public (authorization-code + PKCE) clients and any machine
clients that should call through the gateway.

CLI equivalent: pass the same URL as `customJWTAuthorizer.discoveryUrl` and
the client ids as `allowedClients` in `create-gateway`/`update-gateway`.

## `cognito-m2m-outbound`: the gateway calling a Cognito-protected upstream

1. A confidential app client with `client_credentials`:

   ```hcl
   resource "aws_cognito_user_pool_client" "gateway_outbound" {
     name                                 = "${var.name}-gateway-outbound"
     user_pool_id                         = var.user_pool_id
     generate_secret                      = true
     allowed_oauth_flows                  = ["client_credentials"]
     allowed_oauth_flows_user_pool_client = true
     allowed_oauth_scopes                 = ["https://mcp.example.test/mcp/records.read"]
     supported_identity_providers         = ["COGNITO"]
   }
   ```

2. An OAuth2 credential provider holding it, secrets write-only:

   ```hcl
   resource "aws_bedrockagentcore_oauth2_credential_provider" "cognito" {
     name                       = "${var.name}-cognito"
     credential_provider_vendor = "CustomOauth2"
     oauth2_provider_config {
       custom_oauth2_provider_config {
         client_id_wo                  = aws_cognito_user_pool_client.gateway_outbound.id
         client_secret_wo              = aws_cognito_user_pool_client.gateway_outbound.client_secret
         client_credentials_wo_version = 1
         oauth_discovery {
           discovery_url = "https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/openid-configuration"
         }
       }
     }
   }
   ```

3. The target references it with `credential_provider_configuration { oauth
   { provider_arn = …credential_provider_arn, scopes = [...] } }`, and the
   gateway role may read the provider's `client_secret_arn`.

4. The upstream must accept the new client id: the API Gateway JWT
   authorizer's `audience` and the handler's allowed-client list (`GWY001`).

CLI equivalent (from the AgentCore Cognito guide):

```bash
aws bedrock-agentcore-control create-oauth2-credential-provider \
  --name "<name>-cognito" --credential-provider-vendor "CustomOauth2" \
  --oauth2-provider-config-input '{"customOauth2ProviderConfig": {"oauthDiscovery": {"discoveryUrl": "'$ISSUER_URL'"}, "clientId": "'$CLIENT_ID'", "clientSecret": "'$CLIENT_SECRET'"}}'
```

The AgentCore CLI equivalent is `agentcore add credential --type oauth
--discovery-url … --client-id … --client-secret …`.

## Rotation

Bump `client_credentials_wo_version` after rotating the Cognito client secret;
Terraform then sends the new write-only value. Nothing about the secret is in
state either way.

The provider documentation renders its own example both as
`oauth2_provider_config { custom_oauth2_provider_config { … } }` and, in one
place, with an extra `custom { … }` level; the argument reference lists the
former. Confirm with `terraform providers schema -json` before the first plan.

Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-getting-started-cognito.html,
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_oauth2_credential_provider,
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_gateway_target (read 2026-10-05).

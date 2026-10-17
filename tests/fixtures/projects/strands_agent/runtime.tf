provider "aws" {
  region = "us-east-1"
}

resource "aws_bedrockagentcore_agent_runtime" "library" {
  agent_runtime_name = "library_agent"
  role_arn           = "arn:aws:iam::111122223333:role/library-runtime"
  agent_runtime_artifact {
    container_configuration {
      container_uri = "111122223333.dkr.ecr.us-east-1.amazonaws.com/library:1"
    }
  }
  network_configuration {
    network_mode = "PUBLIC"
  }
  protocol_configuration {
    server_protocol = "HTTP"
  }
}

resource "aws_bedrockagentcore_memory" "library" {
  name                  = "library_memory"
  event_expiry_duration = 30
  encryption_key_arn    = "arn:aws:kms:us-east-1:111122223333:key/example"
}

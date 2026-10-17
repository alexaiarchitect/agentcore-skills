"""The HCL reader: blocks, attributes, literals, comments, heredocs, interpolation."""

from __future__ import annotations

from agentcore_skills import hcl

SAMPLE = '''
# a comment with { braces } that must not count
resource "aws_lambda_function" "mcp" {
  function_name = "${var.name}-mcp"   // trailing comment
  runtime       = "nodejs24.x"
  architectures = ["arm64"]
  timeout       = 29
  publish       = true
  description   = "has a \\"quote\\" and ${var.a == "x" ? "y" : "z"}"
  tracing_config { mode = "Active" }
  environment {
    variables = {
      A = "1"
      B = var.b
    }
  }
  /* block comment
     resource "fake" "x" {} */
}

data "aws_iam_policy_document" "doc" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "p" {
  policy = <<EOT
{"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}
EOT
}
'''


def test_blocks_and_attributes_are_read():
    blocks = hcl.parse(SAMPLE, file="x.tf")
    assert [b.address for b in blocks] == ["aws_lambda_function.mcp", "data.aws_iam_policy_document.doc",
                                           "aws_iam_role_policy.p"]
    fn = blocks[0]
    assert fn.literal("runtime") == "nodejs24.x"
    assert fn.literal("architectures") == ["arm64"]
    assert fn.literal("timeout") == 29 and fn.literal("publish") is True
    assert fn.find("tracing_config").literal("mode") == "Active"
    assert fn.literal("function_name") is None, "an interpolated string is not a literal"
    assert fn.get("function_name") == '"${var.name}-mcp"'
    assert fn.line == 3


def test_comments_never_create_blocks():
    blocks = hcl.parse(SAMPLE)
    assert not any(b.type == "fake" for b in blocks)


def test_heredoc_is_kept_as_one_attribute():
    policy = hcl.parse(SAMPLE)[2].get("policy")
    assert policy.startswith("<<EOT") and "Resource" in policy


def test_nested_map_attribute_is_raw_text():
    env = hcl.parse(SAMPLE)[0].find("environment")
    assert "A = \"1\"" in env.get("variables")


def test_literal_helpers():
    assert hcl.literal('["a", "b"]') == ["a", "b"]
    assert hcl.literal("var.x") is hcl.UNRESOLVED
    assert hcl.literal('["a", var.b]') is hcl.UNRESOLVED
    assert hcl.strings_in('concat(["a"], [var.b, "c"])') == ["a", "c"]
    assert hcl.split_top_level('"a", ["b", "c"], {d = 1}') == ['"a"', '["b", "c"]', '{d = 1}']


def test_unbalanced_input_does_not_raise():
    blocks = hcl.parse('resource "a" "b" {\n  x = "1"\n')
    assert blocks and blocks[0].address == "a.b"


def test_lock_file_versions(fixtures):
    lock = fixtures / "projects" / "vault_like" / "infrastructure" / "live" / "production" / ".terraform.lock.hcl"
    assert hcl.read_lock(lock) == {"registry.terraform.io/hashicorp/aws": "6.55.0"}


def test_project_loading_and_required_providers(fixtures):
    project = hcl.load_project(fixtures / "projects" / "vault_like")
    assert project.required_providers()["aws"]["version"] == "~> 6.0"
    assert project.variable_default("aws_region") == "eu-central-1"
    assert hcl.version_tuple("6.55.0") < hcl.version_tuple("6.64.0")

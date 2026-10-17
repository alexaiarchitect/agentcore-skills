A fixture derived from the first real user's Terraform: two Terragrunt
environments (`live/production` with its provider lock file, `live/hackathon`
without one) and every local module they call, plus the in-repo X-Ray
subsegment emitter and the MCP server's `package.json`. It exists so the
regression tests in `tests/skills/test_friction_regressions.py` replay the
exact situations that produced frictions F13–F17. Every project name, domain
and AWS account id has been replaced (`bookshelf-vault`, `*.bookshelf.example`,
`111122223333`); no secret values were ever present, only variable references.

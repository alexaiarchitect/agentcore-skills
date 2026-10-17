# The plan-only workflow

`gen_ci.py` writes `.github/workflows/agentcore-plan.yml` and
`ci/agentcore/` (an entry point plus a copy of the plugin's stdlib-only
library and data files).

## Triggers

Pull requests that touch the Terraform tree, the workflow or the vendored
checker; and manual dispatch. Plans from forks are skipped (they cannot
assume the OIDC role).

## Jobs

**static** (no AWS credentials):

1. checkout;
2. `python3 ci/agentcore/run.py review . --fail-on error` — the `ACR0xx`
   review; error-level findings fail the job;
3. set up Terraform at the version the root pins (`required_version`), or
   1.14.2;
4. `terraform fmt -check -recursive <tree>`.

**plan** (needs static):

1. checkout, Terraform, `configure-aws-credentials` with
   `role-to-assume: ${{ vars.AWS_PLAN_ROLE_ARN }}` and `id-token: write`;
2. Terragrunt installed from its release with a version and checksum held in
   repository variables (when the root is a Terragrunt stack);
3. `init`, `validate`, `plan -lock-timeout=5m -out=agentcore.tfplan`,
   `show -json agentcore.tfplan > agentcore.plan.json`;
4. `python3 ci/agentcore/run.py policy <root>/agentcore.plan.json`;
5. upload the plan JSON as an artifact (7 days).

## The plan role

Plan reads every resource's current state and the state file, and takes the
state lock. It needs read access to the services in the plan, the state
bucket (and lock), and decrypt on the state key — not write access to
anything else. A deploy role with `service:*` grants (`ACR021` on the first
user's deploy role) must not be reused for plans on pull requests.

## Pins

Action references are read from the repository's existing workflows when
they are pinned to 40-character SHAs, so the new workflow matches the
repository's own supply-chain policy. Otherwise these fallbacks are used —
the pins in the first user's repository on 2026-10-05:

| Action | Pin |
|---|---|
| `actions/checkout` | `11bd71901bbe5b1630ceea73d27597364c9af683` (v4.2.2) |
| `hashicorp/setup-terraform` | `5e8dbf3c6d9deaf4193ca7a8fb23f2ac83bb6c85` (v4.0.0) |
| `aws-actions/configure-aws-credentials` | `acca2b1b2070338fb9fd1ca27ecee81d687e58e5` (v6.1.2) |
| `actions/upload-artifact` | `v4` — replace with a SHA |

## Updating

The vendored library is a copy. After updating the plugin, run
`gen_ci.py --force --dry-run`, read the diff, then write.

Sources: this plugin's `skills/agentcore-ci/scripts/gen_ci.py`; the first user's
plan workflow (private) for pins and Terragrunt installation;
https://developer.hashicorp.com/terraform/cli/commands/plan for saved plans (standard Terraform behaviour, not re-read).

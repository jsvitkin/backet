## ADDED Requirements

### Requirement: Guided deployment MUST use the private GitHub Actions workflow
The system MUST allow the setup wizard to invoke the private bot deployment workflow without changing the privacy boundaries of exported bot bundles.

#### Scenario: Wizard dispatches deploy workflow
- **WHEN** the setup wizard triggers deployment for a configured vault and repository
- **THEN** the GitHub Actions workflow MUST export the private bot bundle, upload it to the Oracle VM, activate the release, restart the bot containers, and run the existing smoke checks

#### Scenario: Workflow artifact remains private
- **WHEN** deployment is triggered by the setup wizard
- **THEN** generated bundle archives and workflow artifacts MUST remain private to the repository workflow and MUST NOT be published to public releases, registries, or images

#### Scenario: Workflow cannot be dispatched
- **WHEN** GitHub Actions cannot dispatch the configured workflow
- **THEN** the setup wizard MUST report the missing workflow, missing permission, unpushed branch, or GitHub authentication problem without producing a partial deploy

### Requirement: Deployment inputs MUST distinguish secrets from variables
The system MUST define which deployment inputs are secrets and which are non-secret variables so guided setup can configure GitHub safely.

#### Scenario: Configure secret deploy inputs
- **WHEN** guided setup configures secret deploy inputs
- **THEN** values that grant access, such as Discord bot tokens, SSH private keys, and private model-download tokens, MUST be stored only as GitHub Actions secrets or equivalent secret storage

#### Scenario: Configure non-secret deploy inputs
- **WHEN** guided setup configures non-secret deploy inputs
- **THEN** facts such as guild ID, Oracle host, Oracle user, compose profile, deploy path, model relative path, and model checksum MAY be stored as committed setup state and GitHub repository variables

#### Scenario: Non-secret fact treated as sensitive
- **WHEN** a user chooses to hide a normally non-secret deploy fact
- **THEN** the setup wizard MUST support storing that fact as a GitHub secret or MUST clearly report that the selected hiding mode is unsupported

#### Scenario: Bundle manifest written
- **WHEN** bot export writes a bundle manifest after guided setup
- **THEN** the manifest MUST include non-secret binding and compatibility metadata but MUST NOT include GitHub secret names as authority or any secret values

### Requirement: Repository prerequisites MUST be machine-checkable
The system MUST expose enough diagnostics for the setup wizard to verify that the private repository can build and deploy the bot bundle.

#### Scenario: Check required repository files
- **WHEN** the setup wizard runs repository doctor checks
- **THEN** it MUST verify that required files are present, including vault Markdown needed for bot indexes, `.backet/config.yaml`, `.backet/state/bot-config.yaml`, `.backet/rules/rules.sqlite3` when rules are enabled, deploy assets, and the deploy workflow file

#### Scenario: Check committed setup files
- **WHEN** setup state or runtime config changed locally
- **THEN** the setup wizard MUST warn that GitHub Actions will not see those changes until they are committed and pushed

#### Scenario: Check workflow push permissions
- **WHEN** the repository contains new or changed files under `.github/workflows/`
- **THEN** deployment setup MUST detect whether the user can push workflow files and MUST explain the required GitHub token scope if not

### Requirement: Oracle deployment prerequisites MUST be doctorable before export
The system MUST let guided setup verify Oracle VM deployment prerequisites before running a private bundle export and upload.

#### Scenario: Remote deploy doctor passes
- **WHEN** the Oracle VM has the expected deploy layout, container runtime, activation scripts, and model cache path
- **THEN** the setup wizard MUST mark Oracle deployment prerequisites ready

#### Scenario: Remote deploy doctor fails
- **WHEN** the Oracle VM is missing required runtime components or paths
- **THEN** the setup wizard MUST report the missing prerequisite and MUST NOT trigger a deployment workflow that is expected to fail for that known reason

#### Scenario: Llama model configured
- **WHEN** setup enables local Llama synthesis
- **THEN** remote deploy doctor MUST verify that the configured model path, checksum, compose profile, and optional model-download token configuration are sufficient for the workflow to bootstrap or reuse the VM-local model cache

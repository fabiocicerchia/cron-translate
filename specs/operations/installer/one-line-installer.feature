@domain:operations @area:installer @from:cron-translate/install
Feature: Installing the CLI with one command
  Lets an operator install cron-translate from the repository with a single piped command, using pipx when available and pip --user otherwise.

  Background:
    Given the operator runs the one-line installer from the README

  @id:operations.installer.001 @rule:operations.installer.prefers-pipx-falls-back-to-pip-user @inferred @source:install.sh#install.sh
  Scenario Outline: The installer uses pipx when present and otherwise installs with pip for the current user
    Given <pipx_state> on the operator's machine
    When the operator runs the installer
    Then cron-translate is installed from the repository's default branch with <installer_command>
    And the operator sees "cron-translate installed. Run: cron-translate --help"

    Examples:
      | pipx_state            | installer_command                                                       |
      | pipx is available     | pipx install git+https://github.com/fabiocicerchia/cron-translate       |
      | pipx is not available | pip install --user git+https://github.com/fabiocicerchia/cron-translate |

  @id:operations.installer.002 @rule:operations.installer.failure-aborts-without-success-message @inferred @source:install.sh#install.sh @questionable
  Scenario: A failed install stops the installer without claiming success
    Given the package installation fails, for example because pip is missing or the repository cannot be reached
    When the operator runs the installer
    Then the installer exits with a non-zero status
    And the operator does not see "cron-translate installed. Run: cron-translate --help"

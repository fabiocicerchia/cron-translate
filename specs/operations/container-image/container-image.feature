@domain:operations @area:container-image @from:cron-translate/dockerfile
Feature: Running the CLI from the container image
  Lets operators run cron-translate from a published container image without installing Python, with the CLI as the image's command and no root privileges.

  Background:
    Given the operator has pulled the cron-translate container image

  @id:operations.container-image.001 @rule:operations.container-image.runs-cli-with-given-arguments @inferred @source:Dockerfile#ENTRYPOINT
  Scenario: Running the image runs the CLI with the arguments given
    When the operator runs the image with the arguments '*/15 9-17 * * 1-5'
    Then the cron-translate CLI runs with '*/15 9-17 * * 1-5' as its arguments
    And the operator sees the same output the installed CLI prints for that expression

  @id:operations.container-image.002 @rule:operations.container-image.runs-as-non-root @inferred @source:Dockerfile#USER
  Scenario: The CLI in the image runs as an unprivileged user
    When the operator runs the image without overriding the user
    Then the CLI process runs as user 'app' with UID 10001
    And the process does not have root privileges inside the container

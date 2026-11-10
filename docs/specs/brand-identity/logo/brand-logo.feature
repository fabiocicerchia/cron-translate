@domain:brand-identity @area:logo @from:stylesheets/extra
Feature: Showing no borrowed logo
  Keeps the docs from presenting a generic theme icon as the project's brand while the project has no logo of its own.

  @id:docs.brand-identity.logo.001 @rule:docs.brand.no-stand-in-logo @inferred @source:docs/stylesheets/extra.css#.md-header__button.md-logo
  Scenario: The header shows no logo while the project has none
    Given the project has no logo configured for its documentation
    When a reader opens any documentation page
    Then the header shows the site name "cron-translate" with no logo icon beside it
    And the navigation drawer title shows no logo icon

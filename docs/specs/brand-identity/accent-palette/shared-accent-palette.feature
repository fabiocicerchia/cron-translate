@domain:brand-identity @area:accent-palette @from:stylesheets/extra
Feature: Keeping the docs and splash page in one colour family
  Gives maintainers and visitors one consistent brand colour across the landing splash and the rendered docs, set in a single place.

  Background:
    Given the project's accent pair is cyan #22d3ee with indigo #6366f1

  @id:docs.brand-identity.accent-palette.001 @rule:docs.brand.single-accent-pair-shared-by-splash-and-docs @inferred @source:docs/stylesheets/extra.css#:root
  Scenario: The splash page and the docs show the same accent colours
    Given the maintainer has changed the accent pair once
    When a visitor opens the splash page and then the documentation
    Then the splash title gradient and buttons use the new accent pair
    And the documentation header, links and highlights use the same accent pair
    And no second copy of the palette needs to be changed

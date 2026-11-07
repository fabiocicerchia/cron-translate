@domain:site-navigation @area:header-tabs @from:stylesheets/extra
Feature: Seeing where you are in the docs
  Helps readers orient themselves by marking the current section and page in the navigation.

  @id:docs.site-navigation.header-tabs.001 @rule:docs.navigation.current-location-emphasised @inferred @source:docs/stylesheets/extra.css#.md-tabs__link--active
  Scenario: The current section tab and page link stand out from the rest
    Given the reader is on the "Dialects" page
    When the reader looks at the top tabs and the side navigation
    Then the "Dialects" tab is shown at full strength while the other tabs are dimmed
    And the "Dialects" link in the side navigation is shown in a heavier weight than its siblings

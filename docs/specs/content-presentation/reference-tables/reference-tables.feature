@domain:content-presentation @area:reference-tables @from:stylesheets/extra
Feature: Reading reference tables on any screen
  Lets readers of the dialect reference read wide tables on narrow screens without losing columns.

  @id:docs.content-presentation.reference-tables.001 @rule:docs.content.tables-scroll-not-clip @inferred @source:docs/stylesheets/extra.css#.md-typeset table:not([class]) @questionable
  Scenario: A table wider than the screen can be scrolled rather than cut off
    Given the "Dialects" page has a table wider than the reader's screen
    When the reader views the table on a narrow screen
    Then the columns beyond the screen edge can be reached by scrolling sideways

@domain:colour-schemes @area:contrast-legibility @from:stylesheets/extra
Feature: Reading the docs in light and dark mode
  Keeps links and page chrome readable for readers whichever colour scheme their system or the toggle selects.

  Background:
    Given the docs follow the reader's system colour scheme, with a manual toggle

  @id:docs.colour-schemes.contrast-legibility.001 @rule:docs.schemes.link-colour-readable-per-scheme @inferred @source:docs/stylesheets/extra.css#[data-md-color-scheme="slate"]
  Scenario Outline: Links use the accent that stays readable on each scheme's background
    Given the reader is viewing the docs in the <scheme> scheme
    When the reader opens a page containing links
    Then links are shown in <link colour>
    And the page background is <background>

    Examples:
      | scheme | link colour    | background                   |
      | light  | indigo #6366f1 | the theme's white background |
      | dark   | cyan #22d3ee   | near-black #0b0f1a           |

@domain:privacy-offline @area:no-external-requests @from:stylesheets/extra
Feature: Reading the docs privately and offline
  Lets readers browse the docs without the page contacting font, CDN or analytics services, so it works offline and leaks nothing.

  @id:docs.privacy-offline.no-external-requests.001 @rule:docs.privacy.no-third-party-requests @inferred @source:docs/stylesheets/extra.css#:root
  Scenario: Docs pages render with system fonts and fetch no web fonts, CDN assets or analytics
    Given the reader's device has no internet connection beyond the docs host
    When the reader opens a documentation page or the splash page
    Then text is set in the device's system font and code in its system monospace font
    And the page makes no requests for web fonts, CDN assets or analytics

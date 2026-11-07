# Specifications of cron-translate / docs

What this code does, one atomic Gherkin scenario per behaviour, read from the code by code-atlas.
Tags: `@verified` a test asserts it · `@inferred` read from the code only · `@gap` an entry point no test covers · `@human` written or amended by a person, never rewritten.

## Brand identity
How the documentation site looks like part of the cron-translate product family.

- **Accent palette**: [Keeping the docs and splash page in one colour family](brand-identity/accent-palette/shared-accent-palette.feature) (1)
- **Logo**: [Showing no borrowed logo](brand-identity/logo/brand-logo.feature) (1)

## Light and dark modes
How the site stays legible whether the reader uses a light, dark or system colour scheme.

- **Contrast and legibility**: [Reading the docs in light and dark mode](colour-schemes/contrast-legibility/scheme-legibility.feature) (1)

## Content presentation
How documentation content such as examples and reference tables is shown on the page.

- **Reference tables**: [Reading reference tables on any screen](content-presentation/reference-tables/reference-tables.feature) (1)

## Privacy and offline use
Promises that the documentation works without contacting outside services.

- **No external requests**: [Reading the docs privately and offline](privacy-offline/no-external-requests/private-offline-docs.feature) (1)

## Site navigation
How readers move around the documentation site.

- **Header and tabs**: [Seeing where you are in the docs](site-navigation/header-tabs/navigation-location-cues.feature) (1)

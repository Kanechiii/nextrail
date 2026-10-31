# Nextrail UI design system

This change adds a shared theme foundation to the established React UI. Dark mode preserves the existing botanical-green presentation. Light mode introduces muted sage, warm-neutral surfaces and readable dark text without replacing the product brand. A native-button theme switch cycles System / Light / Dark, defaults to operating-system preference, responds to system color changes, and stores only the non-sensitive appearance preference in local browser storage.

## Reusable contracts

Shared UI components belong under `apps/web/src/ui`. Product areas must reuse `--nx-page`, `--nx-surface`, `--nx-surface-raised`, `--nx-border`, `--nx-text`, `--nx-muted`, `--nx-accent`, and `--nx-accent-text` rather than inventing section-specific theme palettes. The account workspace is a downstream consumer of these contracts, not an owner of them.

Navigation remains keyboard accessible with native buttons. All motion respects `prefers-reduced-motion`. Focus states must remain visible in both themes. Source-specific visual accents must be supplemental rather than a replacement for system contrast and legibility.

## Scope and verification

This phase establishes shared appearance contracts and theme switching without changing authentication, course sourcing, or private learner state. Automated checks validate theme structure and the existing frontend build. Manual visual, contrast, and mobile-browser audits remain necessary before production release.

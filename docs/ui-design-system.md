# Nextrail UI design system — Learning Route Workspace

This contract documents the unified UI design delivered by the themed learning route
workspace. It supersedes the earlier standalone theme-foundation prototype: do not
import its separate `ThemeSwitch` or `theme.css` files into this interface, because
that would create a second competing set of palette variables and state controls.

## Shared design tokens

The application defines its semantic palette in `apps/web/src/styles.css`.
Both light and dark themes use these tokens; new account-mode views must reuse
them rather than introducing separate hardcoded theme colors.

| CSS token | Meaning |
| --- | --- |
| `--bg` | Workspace page background |
| `--surface` | Raised cards, dialogs, navigation |
| `--secondary` | Quiet secondary surfaces and hover regions |
| `--text` | Primary readable text |
| `--muted` | Secondary labels and descriptions |
| `--primary` | Interactive botanical-green accent |
| `--on-primary` | Accessible foreground over primary accent |
| `--border` | Surface separation and subtle dividers |
| `--control` | Input border contrast |
| `--gold` | Restrained achievement or progress highlights |

The default palette is light; `:root[data-theme=dark]` provides a dark alternative.
Theme preference accepts only `light`, `dark`, or `system`. Invalid saved
preferences revert to `system`. System preference follows the OS color-scheme
change event. Only this appearance preference is persisted in browser storage;
auth bearer tokens remain in memory.

## Accessibility and motion

Use semantic controls (buttons, labels, select and native dialogs) with visible
`:focus-visible` states. Use the existing accessible theme select in the navigation
rather than adding a second theme switch. Honor `prefers-reduced-motion`: CSS
transitions and Anime.js effects should not animate for motion-sensitive users.
Use the established mobile breakpoints instead of adding competing layouts.

## Course/provider accents

Provider branding must be based on verified catalog metadata, never guessed from
provider names or generated dynamically from unverified input. Unknown and synthetic
providers use Nextrail's neutral visual fallback. Course access and certificate
costs are independently represented; unknown values remain unknown.

## Validation

The frontend's Node/Vitest contracts and Playwright desktop/mobile runs cover
guest discovery, account isolation, theme selection, OS theme changes, visual
navigation, reduced-motion behavior, dialogs and responsive layout. Review both
themes manually before release; automated checks do not substitute for visual
contrast and usability review.

These conventions are the design source of truth for later registered-account UI,
learning routes and course card enhancements. No public hosting or paid services
are configured by this document.

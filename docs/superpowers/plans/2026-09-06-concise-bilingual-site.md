# Concise bilingual website

The user requests Terminal-Bench-style concise content, fewer small muted explanations, and theme/language controls. Keep the public “201个高质量任务” wording and all existing scoring/publication safeguards.

Use subagent-driven-development for independent page groups. User has authorized implementation and continued publication; no further approval gate is required.

1. Root: implement a shared preferences provider with Chinese/English and light/dark persistence, system-theme fallback, translated navigation, and CSS theme tokens. Shorten home and task pages, retaining the task distribution.
2. Leaderboard/detail: keep BTS/DRS selection, search, percentages and honest provisional/review statuses. Remove repeated warnings, surface details on demand, translate all user-facing text.
3. Evaluate/docs: simplify the forms and tutorial, preserving working configuration/download/submit commands and explicit Track B simulation. Translate all user-facing copy.
4. Shared interface: `components/preferences.tsx` exports `T({zh,en})`, `useCopy()` returning `(zh,en)=>string`, and `usePreferences()` exposing locale/theme and toggleLocale/toggleTheme. Locale values `zh` / `en`; theme values `light` / `dark`.
5. Validate preferences, existing metric/config tests, TypeScript, app lint, static links, bilingual pages, theme contrast and mobile controls. Commit scoped files, preserve unrelated local work and remote updates, publish, and verify Pages.

Do not change cohort membership, metrics, raw evidence, benchmark model calls or Track B eligibility. No blanket DOM text replacement; translations are explicit React content.

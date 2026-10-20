# Changelog — D&D 2024 Character JSON spec

This spec follows [Semantic Versioning](https://semver.org/):

- **MAJOR** (e.g. 1.x → 2.0.0): breaking changes to field names/shapes. A parser
  written for 1.x may not read a 2.x document.
- **MINOR** (1.0 → 1.1): new optional fields, additive only. 1.x parsers keep working.
- **PATCH** (1.0.0 → 1.0.1): clarifications, docs, constraint fixes — no shape change.

A document declares the version it targets via the top-level `spec_version` field.
Tools should accept any document whose MAJOR matches and whose MINOR is ≤ the
version they implement.

## 1.1.0 — 2026-10-20

Additive live-play and inventory fields. Documents that omit them remain valid
`1.0.0` files; set `spec_version` to `1.1.0` when using the new shapes.

- **`spell_slots` values** may be either an integer total (unchanged from 1.0.0)
  or `{ "total", "expended?" }` so tools can persist spent slots during a session.
- **`resources`**: optional array of `{ "name", "maximum", "current?" }` pools
  (ki, rage, sorcery points, channel divinity, and similar).
- **`prepared_count`**: optional integer preparation budget for prepared casters.
- **`pact_slots`**: optional `{ "total", "expended?", "level?" }` for pact magic.
- **`equipment` items** may be strings (1.0.0) or objects
  `{ "name", "quantity?", "equipped?", "notes?" }`.

See `spec/examples/live-play-state.json` for a minimal document that exercises
the new fields.

## 1.0.0 — 2026-06-15

Initial release.

- Top-level identity: `name`, `player`, `species` (object with `lineage` +
  structured `traits`), `classes` (array, multiclass-ready), `background`,
  `alignment`, `xp`.
- `abilities`, `saving_throws`, `skills` (proficient/expertise), `skill_bonuses`
  (flat feat/item bonuses).
- Combat: `armor_class`, `shield`, `initiative`, `speed` (walk/fly/climb/…),
  `size`, `senses`, `passive_perception`, `hit_points`, `hit_dice`, `death_saves`.
- `proficiencies` (armor/weapons/tools/languages), `weapons`, `feats`,
  `class_features`, `equipment`, `coins`, `attunement`.
- `spellcasting` (DC/attack derived from ability), `spell_slots`, `spells`.
- Designed for D&D 2024 (5.5e): species terminology, expertise, feat-granting
  backgrounds, and homebrew species/feats are all first-class.

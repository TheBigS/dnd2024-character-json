# D&D 2024 Character Sheets

A structured, homebrew-friendly way to store **Dungeons & Dragons 2024 (5.5e)**
player characters as JSON — and turn that JSON into a print-ready PDF character
sheet.

The character data is the source of truth; the PDF is just one rendering of it.
Because the JSON follows a published, versioned [spec](spec/character.schema.json),
other tools can read the same files and render them however they like.

## What this project does

- **Structured storage for 2024 characters.** Ability scores, skills (with
  *expertise*), saves, feats, species traits, spells, equipment — all in one
  tidy JSON file per character.
- **Preserves homebrew & customizations.** Homebrew species, spells, items, etc.
  This project just renders whatever is in the JSON into a character sheet and
  only performs schema validation to ensure it conforms to the 
  [spec](spec/character.schema.json).
- **One source, many layouts.** Today it fills a fillable 2024 PDF sheet. The
  format is a standalone spec, so other converters can target it next — an
  Obsidian wiki stat block, a VTT import, a DM screen summary, a printed 
  booklet, etc.

## Repository layout

| Path | What |
|------|------|
| `characters/*.json` | One file per character |
| `spec/character.schema.json` | The versioned JSON Schema (every field documented + examples). |
| `spec/CHANGELOG.md`, `spec/examples/` | Spec version history and a minimal example. |
| `generate_sheets.py` | Fills a standard 2024 Character sheet PDF template from the JSON. |
| `validate.py` | Checks `characters/` against the spec. |
| `_character_sheet_template.pdf` | The fillable 2024 sheet the generator fills. |
| `output/*.pdf` | Generated sheets are placed here. |

## Getting started

### Option A — Docker (recommended, no Python setup)

```bash
docker build -t dnd-sheets .
docker run --rm -v "$PWD/output:/app/output" dnd-sheets
```

This validates every character against the spec and writes filled PDFs to
`./output/`. Pinned dependencies + a pinned base image mean it builds the same
way years from now.

### Option B — Local Python (3.8+)

```bash
python -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt

python generate_sheets.py          # generate all characters
python generate_sheets.py example-human-fighter   # generate just one
python validate.py                 # validate against the spec
```

## A minimal character

Here's the shape (see [`spec/examples/basic-character.json`](spec/examples/basic-character.json)
for the full, valid file):

```json
{
  "spec_version": "1.0.0",
  "name": "Pip Underbough",
  "species": {
    "name": "Halfling",
    "traits": [
      { "name": "Brave", "description": "Advantage on saves vs. Frightened." }
    ]
  },
  "classes": [ { "name": "Rogue", "level": 1, "hit_die": "d8" } ],
  "background": "Criminal",
  "abilities": { "str": 8, "dex": 16, "con": 14, "int": 12, "wis": 10, "cha": 13 },
  "saving_throws": ["dex", "int"],
  "skills": { "stealth": "expertise", "perception": "proficient" },
  "armor_class": 14,
  "speed": { "walk": 30 },
  "hit_points": { "max": 10 },
  "proficiencies": { "armor": ["light"], "languages": "Common, Halfling" },
  "weapons": [ { "name": "Shortsword", "bonus": "+5", "damage": "1d6+3 Piercing" } ]
}
```

Drop a file like this in `characters/`, run the generator, and a filled sheet
appears in `output/`.

## The JSON format (spec)

- Every field is documented, with examples, in
  [`spec/character.schema.json`](spec/character.schema.json) — a formal
  **JSON Schema (Draft 2020-12)**. Validate any file against it with
  `python validate.py` or an online validator.
- **Versioned with SemVer** via each file's `spec_version`. The **1.x** line only
  adds optional fields (backwards compatible); a **2.0.0** could restructure.
  Tools should accept any document whose major version they support.
- **Built for D&D 2024:** `species` (not "race"), skill *expertise*, weapon
  mastery, feat-granting backgrounds, and homebrew are all expressible — things a
  2014-era schema can't represent.

**1.1.0 live-play fields** (optional, additive): `spell_slots` may use
`{ "total", "expended" }` per level; `resources` tracks class pools (ki, rage,
channel divinity, …); `prepared_count` records a preparation budget; `pact_slots`
covers pact magic; `equipment` entries may be objects with `quantity` / `equipped`
/ `notes`. See `spec/examples/live-play-state.json` and `spec/CHANGELOG.md`.


The spec is self-contained (one schema file with a stable `$id`), so it can move
into its own repository later and be shared by multiple converter projects.

## FAQ

### Why do I need this?
You don't! But if you've ever found yourself tweaking the output of another 
character builder because of some homebrew change, this'll save you a ton of work 
— your character is generated from a clean, well-structured JSON file, so you
edit the data once and regenerate the sheet.

### Do I have to use Docker or Python?
Only to generate the PDF. The JSON itself you can write by hand in any editor —
the tooling is optional. The data is the real product; the generator is just
one way to view it.

### How do I start my own character?
Copy one of the `characters/example-*.json` files, edit the fields, and run the
generator. Every field is documented (with examples) in the 
[schema](spec/character.schema.json), and `python validate.py` will tell you if
anything's off.

### Is the generated PDF editable?
Not really — it's flattened, so it looks identical in every reader (Adobe, Edge,
Firefox, print). You edit the JSON, not the PDF, then regenerate. Think of the
PDF as a printout, not a form.

### What if I don't like the 2024 character sheet?
That's the best part! Because the character lives as JSON, you can convert it 
into whatever format you want. A few we've daydreamed about: Fantasy Stat Block 
format for Obsidian (handy for DMs), VTT import formats, and fully custom sheet 
designs. With one source of truth for the data, every output is just a different 
view of the same JSON.

### The output format I want isn't implemented yet!
Yup, probably true! This repo ships a standard 2024 character sheet PDF generator,
but the JSON is converter-neutral. If you build a new output — or hit a bug, or
need a field the spec can't yet express — open an issue or PR. We're happy to link
your converter here so others can find it instead of reinventing it too.


### Will a future update break my files?
No — the spec uses [SemVer](https://semver.org/). The 1.x line only adds optional
fields (backwards compatible), and each file's `spec_version` tells tools what to
expect. A breaking change would mean a 2.0.0, with a heads-up in the CHANGELOG.

### Does it handle multiclassing or high-level characters?
Yep — `classes` is a list, so multiclassing is built in, and any level works. The
example characters are low-level just to keep them easy to read. This converter 
just validates the JSON character data conforms to the spec, it doesn't do any 
actual rules validation so you are free to do whatever you want (DM approved, of
course).

### Why JSON (and not YAML, TOML, or a database)?
It's universal, git-friendly, human-readable, and validatable against a schema. 
You can hand-edit it, generate it from another tool, diff it in a pull request, 
or parse it in any language.

### Is this written by AI?
Yeah — Claude did a lot of the heavy lifting. I'm a software developer with 20+ 
years of experience, and this is a hobby project. I've deliberately kept the
`Co-Authored-By: Claude` line in the commit messages, because this wasn't purely
hand-written code and I don't want any confusion about what I wrote versus what
the AI did. For me, Claude makes hobby projects like this possible — but I 
completely understand if you feel differently and choose not to use it. I built
this for my own group of players, and I'm sharing it for free in case it helps 
someone else out.

## Prior art & credits

The idea of a shared JSON Schema for D&D characters is well-trodden — see
[BrianWendt/dnd5e_json_schema](https://github.com/BrianWendt/dnd5e_json_schema)
(a 2014-edition 5e schema). This project is a fresh schema focused on the 2024
rules and homebrew, but is inspired by that modular, schema-first spirit.

## License & game content

The **code and JSON schema** in this repository are released under the **Apache
License 2.0** (see [`LICENSE`](LICENSE)).

The **D&D game content** referenced here — spell, class, species, feat, and
background names and the short rules summaries, as used in the example characters
and the schema's examples — is drawn from the **System Reference Document 5.2**
and used under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/legalcode):

> This work includes material from the System Reference Document 5.2 ("SRD 5.2")
> by Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd. The
> SRD 5.2 is licensed under the Creative Commons Attribution 4.0 International
> License, available at https://creativecommons.org/licenses/by/4.0/legalcode.

The fillable PDF template (`_character_sheet_template.pdf`) is a third-party
character sheet, included for convenience and not covered by this repository's
license.

---

<p align="center">Built with ❤️ for the D&D community</p>

#!/usr/bin/env python3
"""
D&D 2024 Character Sheet Generator
==================================
Reads JSON character data from characters/ and fills the fillable D&D 2024
character sheet template to produce print-ready PDFs.

Workflow:
  1. Edit JSON files in characters/ (one per player character)
  2. Run this script:        python generate_sheets.py
     or one character only:  python generate_sheets.py example-human-fighter
  3. Output PDFs appear in output/

Requires: pypdf  (pip install pypdf)

Compatible with Python 3.7+

--------------------------------------------------------------------------
JSON FORMAT
--------------------------------------------------------------------------
Character files conform to the "D&D 2024 Character JSON" spec, fully documented
(every field, with examples) in  spec/character.schema.json  — a formal JSON
Schema (Draft 2020-12), SemVer-versioned via each file's `spec_version`.
See spec/examples/basic-character.json for a minimal example.

Shape, in brief:
  name, player, species{name,lineage,traits[]}, classes[{name,subclass,level,
  hit_die}], background, alignment, xp,
  abilities{str..cha}, saving_throws[], skills{skill: proficient|expertise},
  skill_bonuses{skill: int},
  armor_class, shield, initiative, speed{walk,fly,climb,...}, size,
  senses{darkvision,...}, passive_perception,
  hit_points{max,current,temp}, hit_dice{die,total,spent}, death_saves{},
  proficiencies{armor[],weapons,tools,languages},
  weapons[], feats[{name,description}], class_features[{name,description}],
  equipment[] (string or {name,quantity?,equipped?,notes?}), coins{}, attunement[],
  spellcasting{ability}, spell_slots{} (int total or {total,expended?}),
  pact_slots?, resources?, prepared_count?, spells[]

Derived (not stored): ability modifiers; proficiency bonus (from level if
omitted); spell save DC / attack bonus (from the spellcasting ability).
--------------------------------------------------------------------------
"""

import json
import math
import os
import sys
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    print("ERROR: pypdf is not installed.")
    print("  Install it with:  pip install pypdf")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Field-name mappings  (template field name -> JSON path or computed value)
# ---------------------------------------------------------------------------

# Ability score short names -> modifier calculation
ABILITY_SHORT = ["str", "dex", "con", "int", "wis", "cha"]
ABILITY_NAMES = {
    "str": "Strength", "dex": "Dexterity", "con": "Constitution",
    "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma",
}

def ability_mod(score):
    """Standard D&D ability modifier."""
    return (score - 10) // 2

def fmt_mod(mod):
    """Format a modifier as +N or -N."""
    return "+{}".format(mod) if mod >= 0 else str(mod)

def ability_key(name):
    """Normalize an ability given as a short key or full name -> short key."""
    if not name:
        return None
    s = str(name).strip().lower()
    if s in ABILITY_NAMES:
        return s
    for k, v in ABILITY_NAMES.items():
        if v.lower() == s:
            return k
    return s[:3]  # best effort


# Checkbox field names for SAVING THROW proficiencies
SAVE_PROF_CHECKBOXES = {
    "str": "Check Box18",
    "dex": "Check Box11",
    "con": "Check Box7",
    "int": "Check Box25",
    "wis": "Check Box17",
    "cha": "Check Box6",
}

# Checkbox field names for SKILL proficiencies
SKILL_PROF_CHECKBOXES = {
    "acrobatics":      "Check Box8",
    "animal_handling": "Check Box15",
    "arcana":          "Check Box24",
    "athletics":       "Check Box19",
    "deception":       "Check Box5",
    "history":         "Check Box20",
    "insight":         "Check Box13",
    "intimidation":    "Check Box4",
    "investigation":   "Check Box21",
    "medicine":        "Check Box12",
    "nature":          "Check Box22",
    "perception":      "Check Box14",
    "performance":     "Check Box3",
    "persuasion":      "Check Box2",
    "religion":        "Check Box23",
    "sleight_of_hand": "Check Box9",
    "stealth":         "Check Box10",
    "survival":        "Check Box16",
}

# Skill -> ability used
SKILL_ABILITY = {
    "acrobatics": "dex", "animal_handling": "wis", "arcana": "int",
    "athletics": "str", "deception": "cha", "history": "int",
    "insight": "wis", "intimidation": "cha", "investigation": "int",
    "medicine": "wis", "nature": "int", "perception": "wis",
    "performance": "cha", "persuasion": "cha", "religion": "int",
    "sleight_of_hand": "dex", "stealth": "dex", "survival": "wis",
}

# Skill -> text field name on the PDF
SKILL_TEXT_FIELDS = {
    "acrobatics": "ACROBATICS", "animal_handling": "ANIMAL HANDLING",
    "arcana": "ARCANA", "athletics": "ATHLETICS", "deception": "DECEPTION",
    "history": "HISTORY", "insight": "INSIGHT", "intimidation": "INTIMIDATE",
    "investigation": "INVESTIGATION", "medicine": "MEDICINE", "nature": "NATURE",
    "perception": "PERCEPTION", "performance": "PERFORMANCE",
    "persuasion": "PERSUASION", "religion": "RELIGION",
    "sleight_of_hand": "SLEIGHT OF HAND", "stealth": "STEALTH",
    "survival": "SURVIVAL",
}

# Armor training checkboxes
ARMOR_CHECKBOXES = {
    "light":   "Check Box33",
    "medium":  "Check Box34",
    "heavy":   "Check Box35",
    "shields": "Check Box36",
}

# Death save checkboxes, in fill order (left -> center -> right)
DEATH_SAVE_SUCCESS = ["SUCCESS LEFT L chk", "SUCCESS CTR chk", "SUCCESS RIGHT chk"]
DEATH_SAVE_FAILURE = ["FAILURE LEFT chk", "FAILURE CTR chk", "FAILURE RIGHT chk"]

# Text fields that fill_pdf() makes multiline + auto-sizing, so text wraps and
# shrinks to fit instead of overflowing (long prose / list fields).
FLOW_TEXT_FIELDS = {
    "SPECIES TRAITS", "FEATS", "CLASS FEATURES 1", "CLASS FEATURES 2",
    "WEAPON PROF", "TOOL PROF", "LANGUAGES", "EQUIPMENT", "PERSONALITY",
}

# Fields rendered with our own centered, auto-fit appearance, keyed by max font
# size. pypdf is weak here: it ignores "\n" (SPEED's two lines) and caps
# auto-size at 12pt (tiny in the big HP boxes). Ours wraps on "\n", auto-fits to
# the box, and centers vertically + horizontally.
CUSTOM_TEXT_FIELDS = {
    "SPEED": 11.0,
    "Current HP": 24.0,
    "Max HP": 13.0,
    "Temp HP": 15.0,
}

# Spell row C/R/M checkbox field names (3 per row, 29 rows)
# Row 0 is the first spell row (SPELL NAME), rows 1-28 are SPELL NAME0-SPELL NAME28
# Based on position analysis: each row has 3 checkboxes at x~239 (C), x~261 (R), x~283 (M)
SPELL_CRM_CHECKBOXES = {
    0:  ("Check Box0",   "Check Box59", "Check Box60"),    # Row 0  (SPELL NAME)
    1:  ("Check Box64",  "Check Box65", "Check Box66"),    # Row 1  (SPELL NAME0)
    2:  ("Check Box67",  "Check Box69", None),             # Row 2  (SPELL NAME1) - only 2 visible
    3:  ("Check Box70",  "Check Box72", None),             # Row 3  (SPELL NAME4)
    4:  ("Check Box73",  "Check Box75", None),             # Row 4  (SPELL NAME3)
    5:  ("Check Box76",  "Check Box77", "Check Box78"),    # Row 5  (SPELL NAME2)
    6:  ("Check Box79",  "Check Box80", "Check Box81"),    # Row 6  (SPELL NAME7)
    7:  ("Check Box85",  "Check Box86", "Check Box87"),    # Row 7  (SPELL NAME6)
    8:  ("Check Box82",  "Check Box83", "Check Box84"),    # Row 8  (SPELL NAME5)
    9:  ("Check Box88",  "Check Box89", "Check Box90"),    # Row 9  (SPELL NAME10)
    10: ("Check Box91",  "Check Box92", "Check Box93"),    # Row 10 (SPELL NAME9)
    11: ("Check Box94",  "Check Box95", "Check Box96"),    # Row 11 (SPELL NAME8)
    12: ("Check Box97",  "Check Box98", "Check Box99"),    # Row 12 (SPELL NAME13)
    13: ("Check Box100", "Check Box101","Check Box102"),   # Row 13 (SPELL NAME12)
    14: ("Check Box103", "Check Box104","Check Box105"),   # Row 14 (SPELL NAME11)
    15: ("Check Box106", "Check Box107","Check Box108"),   # Row 15 (SPELL NAME16)
    16: ("Check Box109", "Check Box110","Check Box111"),   # Row 16 (SPELL NAME15)
    17: ("Check Box112", "Check Box113","Check Box114"),   # Row 17 (SPELL NAME14)
    18: ("Check Box115", "Check Box116","Check Box117"),   # Row 18 (SPELL NAME19)
    19: ("Check Box118", "Check Box119","Check Box120"),   # Row 19 (SPELL NAME18)
    20: ("Check Box121", "Check Box122","Check Box123"),   # Row 20 (SPELL NAME17)
    21: ("Check Box124", "Check Box125","Check Box126"),   # Row 21 (SPELL NAME22)
    22: ("Check Box127", "Check Box128","Check Box129"),   # Row 22 (SPELL NAME21)
    23: ("Check Box130", "Check Box131","Check Box132"),   # Row 23 (SPELL NAME20)
    24: ("Check Box133", "Check Box134","Check Box135"),   # Row 24 (SPELL NAME25)
    25: ("Check Box136", "Check Box137","Check Box138"),   # Row 25 (SPELL NAME24)
    26: ("Check Box139", "Check Box140","Check Box141"),   # Row 26 (SPELL NAME23)
    27: ("Check Box142", "Check Box143","Check Box144"),   # Row 27 (SPELL NAME28)
    28: ("Check Box145", "Check Box146","Check Box147"),   # Row 28 (SPELL NAME27)
}

# Spell slot expended checkboxes (spell level -> list of checkbox names)
# Each level has a row of diamond checkboxes for tracking expended slots
SPELL_SLOT_EXPENDED = {
    1: ["Check Box52", "Check Box46", "Check Box40", "Check Box37"],      # LVL1: 4 slots max
    2: ["Check Box49", "Check Box38", "Check Box43"],                     # LVL2: 3 slots max
    3: ["Check Box47", "Check Box44", "Check Box41"],                     # LVL3: 3 slots max
    4: ["Check Box50", "Check Box53", "Check Box39"],                     # LVL4: 3 slots max
    5: ["Check Box48", "Check Box42"],                                    # LVL5: 3 slots max (approx)
    6: ["Check Box51", "Check Box54"],                                    # LVL6: 2 slots max
    7: ["Check Box55", "Check Box56"],                                    # LVL7: 2 slots max
    8: ["Check Box45", "Check Box58"],                                    # LVL8: 1 slot
    9: ["Check Box57"],                                                   # LVL9: 1 slot
}

# The spell field names in the PDF are oddly ordered. This maps the visual
# row index (0=top row, 1=second row, etc.) to the PDF field suffix.
# Row 0 uses unsuffixed names (SPELL NAME, SPELL LEVEL, etc.)
# Other rows use numbered suffixes but NOT in visual order.
SPELL_ROW_SUFFIX = {
    0:  "",    # top row
    1:  "0",
    2:  "1",
    3:  "4",
    4:  "3",
    5:  "2",
    6:  "7",
    7:  "6",
    8:  "5",
    9:  "10",
    10: "9",
    11: "8",
    12: "13",
    13: "12",
    14: "11",
    15: "16",
    16: "15",
    17: "14",
    18: "19",
    19: "18",
    20: "17",
    21: "22",
    22: "21",
    23: "20",
    24: "25",
    25: "24",
    26: "23",
    27: "28",
    28: "27",
}

# Note: Row 29 would be suffix "26" but we only have 29 rows (0-28).


def get_spell_field(base_name, row_index):
    """Get the PDF field name for a spell field at the given visual row."""
    suffix = SPELL_ROW_SUFFIX.get(row_index, str(row_index))
    return base_name + suffix


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def total_level(char):
    """Sum of all class levels (1 if none listed)."""
    return sum(c.get("level", 0) for c in char.get("classes", [])) or 1


def derive_prof_bonus(char):
    """Stored proficiency_bonus, else computed from total level."""
    if "proficiency_bonus" in char:
        return char["proficiency_bonus"]
    return 2 + (total_level(char) - 1) // 4


def format_speed(speed):
    """{walk:30, fly:30} -> '30 ft. (Fly 30 ft.)'."""
    if not speed:
        return "30 ft."
    s = "{} ft.".format(speed.get("walk", 30))
    extras = []
    for key, label in [("fly", "Fly"), ("climb", "Climb"), ("swim", "Swim"), ("burrow", "Burrow")]:
        if speed.get(key):
            extras.append("{} {} ft.".format(label, speed[key]))
    if extras:
        # Put the extra speeds on their own line so the (small) SPEED box can
        # use a bigger font than it could with everything on one line.
        s += "\n(" + ", ".join(extras) + ")"
    return s


def species_display(species):
    """{name:'Elf', lineage:'Wood Elf'} -> 'Elf (Wood Elf)'."""
    species = species or {}
    name = species.get("name", "")
    lineage = species.get("lineage", "")
    return "{} ({})".format(name, lineage) if lineage else name


def join_features(items):
    """Render [{name, description}] into the template's blocky text style.
    A feature named 'Note' renders as just its description (a bare aside)."""
    parts = []
    for it in items or []:
        name = (it.get("name") or "").strip()
        desc = (it.get("description") or "").strip()
        if name and name.lower() != "note":
            parts.append("{}: {}".format(name, desc) if desc else name)
        else:
            parts.append(desc)
    return "\n\n".join(p for p in parts if p)


def spell_slot_counts(entry):
    """Normalize a spell_slots value to (total, expended).

    Accepts the 1.0 integer form or the 1.1 object form {total, expended?}.
    """
    if isinstance(entry, dict):
        total = int(entry.get("total") or 0)
        expended = int(entry.get("expended") or 0)
        if expended < 0:
            expended = 0
        if expended > total:
            expended = total
        return total, expended
    try:
        total = int(entry or 0)
    except (TypeError, ValueError):
        total = 0
    return max(0, total), 0


def format_equipment_line(item):
    """Render a string or structured equipment entry as one inventory line."""
    if isinstance(item, dict):
        name = (item.get("name") or "").strip() or "Item"
        qty = item.get("quantity")
        try:
            qty_n = int(qty) if qty is not None else 1
        except (TypeError, ValueError):
            qty_n = 1
        line = "{} ({})".format(name, qty_n) if qty_n != 1 else name
        if item.get("equipped"):
            line = "{} [equipped]".format(line)
        notes = (item.get("notes") or "").strip()
        if notes:
            line = "{} — {}".format(line, notes)
        return line
    return str(item)


def validate_character(char):
    """Return a list of human-readable warning strings (does not raise)."""
    warnings = []

    abilities = char.get("abilities", {})
    for ab in ABILITY_SHORT:
        if ab not in abilities:
            warnings.append("missing ability score '{}'".format(ab))

    if not char.get("classes"):
        warnings.append("no classes listed")

    for ab in char.get("saving_throws", []):
        if ability_key(ab) not in ABILITY_NAMES:
            warnings.append("unknown saving throw '{}'".format(ab))

    skills = char.get("skills", {}) or {}
    for sk in list(skills.keys()) + list(char.get("skill_bonuses", {}).keys()):
        if sk not in SKILL_ABILITY:
            warnings.append("unknown skill '{}' (use snake_case)".format(sk))
    for sk, lvl in skills.items():
        if lvl not in ("proficient", "expertise"):
            warnings.append("skill '{}' level must be proficient|expertise, got '{}'".format(sk, lvl))

    for at in (char.get("proficiencies", {}) or {}).get("armor", []):
        if str(at).lower() not in ARMOR_CHECKBOXES:
            warnings.append("unknown armor training '{}'".format(at))

    for i, w in enumerate(char.get("weapons", [])):
        if not w.get("name"):
            warnings.append("weapon row {} has no name".format(i + 1))
    if len(char.get("weapons", [])) > 6:
        warnings.append("more than 6 weapons; only the first 6 are printed")

    spells = char.get("spells", [])
    if len(spells) > 29:
        warnings.append("more than 29 spells; only the first 29 are printed")
    for sp in spells:
        if "TODO" in sp.get("name", "").upper():
            warnings.append("spell still has a TODO placeholder: '{}'".format(sp.get("name")))

    sc = char.get("spellcasting") or {}
    if sc and ability_key(sc.get("ability")) not in ABILITY_NAMES:
        warnings.append("spellcasting ability '{}' is not a valid ability".format(sc.get("ability")))

    return warnings


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def compute_fields(char):
    """
    Take a character JSON dict and return a dict of
    {pdf_field_name: value} ready to write into the template.
    """
    fields = {}
    checks = {}  # checkbox fields: name -> True / "P" / "E"

    abilities = char.get("abilities", {})
    prof = derive_prof_bonus(char)
    classes = char.get("classes", [])

    # --- Header ---
    fields["Name"] = char.get("name", "")
    fields["Class"] = " / ".join(c.get("name", "") for c in classes)
    fields["Subclass"] = " / ".join(c.get("subclass", "") for c in classes if c.get("subclass"))
    fields["Level"] = str(total_level(char))
    fields["Background"] = char.get("background", "")
    fields["Species"] = species_display(char.get("species"))
    fields["XP Points"] = str(char.get("xp", "(Milestone)"))

    # --- Combat stats ---
    fields["Armor Class"] = str(char.get("armor_class", ""))
    checks["shield chk"] = char.get("shield", False)
    init = char.get("initiative")
    if init is None:
        init = ability_mod(abilities.get("dex", 10))
    fields["init"] = fmt_mod(init)
    fields["SPEED"] = format_speed(char.get("speed"))
    fields["SIZE"] = char.get("size", "Medium")

    # --- HP & hit dice ---
    hp = char.get("hit_points", {}) or {}
    fields["Max HP"] = str(hp.get("max", ""))
    fields["Current HP"] = str(hp.get("current", hp.get("max", "")))
    fields["Temp HP"] = str(hp.get("temp", "") or "")
    hd = char.get("hit_dice", {}) or {}
    fields["Max HD"] = "{}{}".format(hd["total"], hd["die"]) if hd.get("die") and hd.get("total") else ""
    fields["Spent HD"] = str(hd.get("spent", "") or "")

    # --- Death saves ---
    ds = char.get("death_saves", {}) or {}
    for i, box in enumerate(DEATH_SAVE_SUCCESS):
        checks[box] = i < int(ds.get("successes", 0) or 0)
    for i, box in enumerate(DEATH_SAVE_FAILURE):
        checks[box] = i < int(ds.get("failures", 0) or 0)

    # --- Proficiency bonus ---
    fields["PROF BONUS"] = fmt_mod(prof)

    # --- Ability scores, modifiers, saves ---
    save_profs = set(ability_key(a) for a in char.get("saving_throws", []))

    score_fields = {
        "str": ("STR SCORE", "STR MOD", "STR SAVE"),
        "dex": ("DEX SCORE", "DEX MOD", "DEX SAVE"),
        "con": ("CON SCORE", "CON MOD", "CON SAVE"),
        "int": ("INT SCORE", "INT MOD", "INT SAVE"),
        "wis": ("WIS SCORE", "WIS MOD", "Text Field71"),  # WIS SAVE is "Text Field71"
        "cha": ("CHA SCORE", "CHA MOD", "CHA SAVE"),
    }

    for ab in ABILITY_SHORT:
        score = abilities.get(ab, 10)
        mod = ability_mod(score)
        score_f, mod_f, save_f = score_fields[ab]
        fields[score_f] = str(score)
        fields[mod_f] = fmt_mod(mod)

        save_val = mod + (prof if ab in save_profs else 0)
        fields[save_f] = fmt_mod(save_val)

        # Save proficiency checkbox — render "P" to match the skill dots
        if ab in save_profs:
            checks[SAVE_PROF_CHECKBOXES[ab]] = "P"

    # --- Skills ---
    skills_map = char.get("skills", {}) or {}
    skill_profs = {k for k, v in skills_map.items() if v == "proficient"}
    skill_expertise = {k for k, v in skills_map.items() if v == "expertise"}
    skill_bonuses = char.get("skill_bonuses", {}) or {}

    for skill, ab in SKILL_ABILITY.items():
        score = abilities.get(ab, 10)
        mod = ability_mod(score)
        bonus = mod
        if skill in skill_expertise:
            bonus += prof * 2
        elif skill in skill_profs:
            bonus += prof
        bonus += skill_bonuses.get(skill, 0)  # flat feat/item bonuses (e.g. Magician)
        fields[SKILL_TEXT_FIELDS[skill]] = fmt_mod(bonus)

        # Mark the dot "E" for expertise, "P" for proficiency (instead of a plain X)
        if skill in skill_expertise:
            checks[SKILL_PROF_CHECKBOXES[skill]] = "E"
        elif skill in skill_profs:
            checks[SKILL_PROF_CHECKBOXES[skill]] = "P"

    # --- Passive perception (computed from Perception if not stored) ---
    pp = char.get("passive_perception")
    if pp is None:
        per = ability_mod(abilities.get("wis", 10))
        if "perception" in skill_expertise:
            per += prof * 2
        elif "perception" in skill_profs:
            per += prof
        per += skill_bonuses.get("perception", 0)
        pp = 10 + per
    fields["PASSIVE PERCEPTION"] = str(pp)

    # --- Proficiencies (armor training + weapon/tool/language text) ---
    profs = char.get("proficiencies", {}) or {}
    for armor_type in profs.get("armor", []):
        key = str(armor_type).lower()
        if key in ARMOR_CHECKBOXES:
            checks[ARMOR_CHECKBOXES[key]] = True
    fields["WEAPON PROF"] = profs.get("weapons", "")
    fields["TOOL PROF"] = profs.get("tools", "")
    fields["LANGUAGES"] = profs.get("languages", "")

    # --- Weapons table ---
    weapons = char.get("weapons", [])
    for i, w in enumerate(weapons[:6], start=1):
        fields["NAME - WEAPON {}".format(i)] = w.get("name", "")
        fields["BONUS/DC - WEAPON {}".format(i)] = w.get("bonus", "")
        fields["DAMAGE/TYPE - WEAPON {}".format(i)] = w.get("damage", "")
        fields["NOTES - WEAPON {}".format(i)] = w.get("notes", "")

    # --- Features / Traits (arrays of {name, description} -> blocky text) ---
    fields["SPECIES TRAITS"] = join_features((char.get("species") or {}).get("traits", []))
    fields["FEATS"] = join_features(char.get("feats", []))
    fields["CLASS FEATURES 1"] = join_features(char.get("class_features", []))
    fields["CLASS FEATURES 2"] = ""

    # --- Equipment & Personality ---
    fields["EQUIPMENT"] = "\n".join(
        format_equipment_line(item) for item in (char.get("equipment", []) or [])
    )
    fields["PERSONALITY"] = char.get("personality", "")

    # --- Coins ---
    coins = char.get("coins", {})
    for coin in ["cp", "sp", "ep", "gp", "pp"]:
        val = coins.get(coin, 0)
        fields[coin.upper()] = str(val) if val else ""

    # --- Attunement ---
    attune = char.get("attunement", [])
    for i, item in enumerate(attune[:3], start=1):
        fields["ATTUNMENT {}".format(i)] = item

    # --- Spellcasting (modifier / DC / attack are computed from the ability) ---
    sc = char.get("spellcasting") or {}
    if sc and sc.get("ability"):
        ak = ability_key(sc.get("ability"))
        amod = ability_mod(abilities.get(ak, 10)) if ak in ABILITY_NAMES else 0
        mod_val = sc.get("modifier", amod)
        save_dc = sc.get("save_dc", 8 + prof + amod)
        atk = sc.get("attack_bonus", prof + amod)
        fields["SPELLCASTING ABILITY"] = ABILITY_NAMES.get(ak, str(sc.get("ability")))
        fields["SPELLCASTING MOD"] = fmt_mod(mod_val) if isinstance(mod_val, int) else str(mod_val)
        fields["SPELL SAVE DC"] = str(save_dc)
        fields["SPELL ATTACK BONUS"] = fmt_mod(atk) if isinstance(atk, int) else str(atk)

    # --- Spell slots (int total, or {total, expended} from spec 1.1.0) ---
    slots = char.get("spell_slots", {}) or {}
    for lvl in range(1, 10):
        key = str(lvl)
        if key not in slots:
            continue
        total, expended = spell_slot_counts(slots[key])
        fields["LVL{} TOTAL".format(lvl)] = str(total)
        boxes = SPELL_SLOT_EXPENDED.get(lvl, [])
        for i, box in enumerate(boxes):
            if i < expended:
                checks[box] = True

    # --- Spells ---
    spells = char.get("spells", [])
    for i, spell in enumerate(spells[:29]):
        row = i
        suffix = SPELL_ROW_SUFFIX.get(row, str(row))
        fields["SPELL LEVEL" + suffix] = spell.get("level", "")
        fields["SPELL NAME" + suffix] = spell.get("name", "")
        fields["CASTING TIME" + suffix] = spell.get("casting_time", "")
        fields["RANGE" + suffix] = spell.get("range", "")
        fields["SPELL NOTES" + suffix] = spell.get("notes", "")

        # C/R/M checkboxes
        crm = SPELL_CRM_CHECKBOXES.get(row)
        if crm:
            c_box, r_box, m_box = crm
            if c_box and spell.get("concentration", False):
                checks[c_box] = True
            if r_box and spell.get("ritual", False):
                checks[r_box] = True
            if m_box and spell.get("material", False):
                checks[m_box] = True

    return fields, checks


def _letter_appearance(writer, letter, bbox, font_ref):
    """Build a checkbox 'on' appearance XObject that draws a single letter
    (e.g. 'P' for proficiency, 'E' for expertise) centered in the box."""
    from pypdf.generic import (
        DecodedStreamObject, DictionaryObject, ArrayObject,
        NameObject, NumberObject, FloatObject,
    )
    w = float(bbox[2]) - float(bbox[0])
    h = float(bbox[3]) - float(bbox[1])
    size = round(h * 0.82, 2)                 # fill most of the box height
    tx = max(0.4, (w - size * 0.60) / 2.0)    # ~0.60 em advance, roughly centered
    ty = max(0.4, (h - size * 0.72) / 2.0)    # ~0.72 cap height
    content = ("/Tx BMC\nq\nBT\n/Helv %.2f Tf\n0 0 0 rg\n%.2f %.2f Td\n(%s) Tj\nET\nQ\nEMC\n"
               % (size, tx, ty, letter))
    s = DecodedStreamObject()
    s.set_data(content.encode("latin-1"))
    s[NameObject("/Type")] = NameObject("/XObject")
    s[NameObject("/Subtype")] = NameObject("/Form")
    s[NameObject("/FormType")] = NumberObject(1)
    s[NameObject("/BBox")] = ArrayObject([FloatObject(x) for x in bbox])
    s[NameObject("/Matrix")] = ArrayObject([NumberObject(1), NumberObject(0),
                                            NumberObject(0), NumberObject(1),
                                            NumberObject(0), NumberObject(0)])
    s[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/Helv"): font_ref})
    })
    return writer._add_object(s)


def _filled_star_appearance(writer, bbox):
    """Build a checkbox 'on' appearance that draws a solid filled 4-pointed
    star (sparkle), matching the template's diamond/star outline so the whole
    shape reads as filled-in. Vector path -> crisp and font-independent."""
    from pypdf.generic import (
        DecodedStreamObject, DictionaryObject, ArrayObject,
        NameObject, NumberObject, FloatObject,
    )
    w = float(bbox[2]) - float(bbox[0])
    h = float(bbox[3]) - float(bbox[1])
    cx, cy = w / 2.0, h / 2.0
    ox, oy = 0.44 * w, 0.44 * h     # outer tips (just inside the outline points)
    kx, ky = 0.12 * w, 0.12 * h     # control offset -> concave (sparkle) sides
    T, R, B, L = (cx, cy + oy), (cx + ox, cy), (cx, cy - oy), (cx - ox, cy)
    # each quarter is one cubic Bezier from tip to tip, bowed in toward center
    content = (
        "/Tx BMC\nq\n0 0 0 rg\n"
        "%.3f %.3f m\n" % T +
        "%.3f %.3f %.3f %.3f %.3f %.3f c\n" % (cx + kx, cy + ky, cx + kx, cy + ky, R[0], R[1]) +
        "%.3f %.3f %.3f %.3f %.3f %.3f c\n" % (cx + kx, cy - ky, cx + kx, cy - ky, B[0], B[1]) +
        "%.3f %.3f %.3f %.3f %.3f %.3f c\n" % (cx - kx, cy - ky, cx - kx, cy - ky, L[0], L[1]) +
        "%.3f %.3f %.3f %.3f %.3f %.3f c\n" % (cx - kx, cy + ky, cx - kx, cy + ky, T[0], T[1]) +
        "h\nf\nQ\nEMC\n"
    )
    s = DecodedStreamObject()
    s.set_data(content.encode("latin-1"))
    s[NameObject("/Type")] = NameObject("/XObject")
    s[NameObject("/Subtype")] = NameObject("/Form")
    s[NameObject("/FormType")] = NumberObject(1)
    s[NameObject("/BBox")] = ArrayObject([FloatObject(x) for x in bbox])
    s[NameObject("/Matrix")] = ArrayObject([NumberObject(1), NumberObject(0),
                                            NumberObject(0), NumberObject(1),
                                            NumberObject(0), NumberObject(0)])
    s[NameObject("/Resources")] = DictionaryObject({})
    return writer._add_object(s)


def _apply_marker_appearances(writer, markers):
    """Replace the 'on' appearance of the given checkboxes.
    markers maps field name -> 'P' / 'E' (a letter) or 'dot' (a filled circle)."""
    from pypdf.generic import DictionaryObject, NameObject

    # Helvetica-Bold WITH an encoding, so the P/E glyphs render in strict
    # viewers (Adobe shows nothing for a non-embedded font lacking /Encoding).
    font_ref = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica-Bold"),
        NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
    }))

    for page in writer.pages:
        for annot in page.get("/Annots", []) or []:
            o = annot.get_object()
            name = o.get("/T")
            if name is None and o.get("/Parent") is not None:
                name = o.get("/Parent").get_object().get("/T")
            name = str(name) if name is not None else None
            if name not in markers:
                continue
            bbox = [0, 0, 7.75, 7.75]
            ap = o.get("/AP")
            n = ap.get_object().get("/N").get_object() if ap and "/N" in ap.get_object() else None
            if n is not None and n.get("/Yes") is not None:
                bb = n["/Yes"].get_object().get("/BBox")
                if bb:
                    bbox = [float(x) for x in bb]
                mk = markers[name]
                if mk in ("P", "E"):
                    new_ap = _letter_appearance(writer, mk, bbox, font_ref)
                else:
                    new_ap = _filled_star_appearance(writer, bbox)
                n[NameObject("/Yes")] = new_ap
                o[NameObject("/AS")] = NameObject("/Yes")


def _text_block_appearance(writer, bbox, text, q, max_size, font_ref):
    """Custom text-field /AP that renders `text` (split on '\\n') as separate,
    vertically-centered lines, auto-fit to the box. q=1 centers each line.
    Used for the small SPEED box so a two-line value stays readable."""
    from pypdf.generic import (
        DecodedStreamObject, DictionaryObject, ArrayObject,
        NameObject, NumberObject, FloatObject,
    )
    w = float(bbox[2]) - float(bbox[0])
    h = float(bbox[3]) - float(bbox[1])
    lines = text.split("\n")
    n = max(1, len(lines))
    CW, LH, pad = 0.48, 1.18, 1.5     # avg char width (em), line-height, padding
    maxlen = max((len(ln) for ln in lines), default=1) or 1
    size = min(max_size, (w - 2 * pad) / (maxlen * CW), (h - 2 * pad) / (n * LH))
    size = max(4.0, size)
    line_h = size * LH
    block_h = n * line_h

    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    ops = ["/Tx BMC", "q", "BT", "/Helv %.2f Tf 0 0 0 rg" % size]
    for i, ln in enumerate(lines):
        lw = len(ln) * CW * size
        x = (w - lw) / 2.0 if q == 1 else pad
        y = (h + block_h) / 2.0 - (i + 1) * line_h + 0.25 * size
        ops.append("1 0 0 1 %.2f %.2f Tm (%s) Tj" % (x, y, esc(ln)))
    ops += ["ET", "Q", "EMC"]

    s = DecodedStreamObject()
    s.set_data(("\n".join(ops) + "\n").encode("latin-1"))
    s[NameObject("/Type")] = NameObject("/XObject")
    s[NameObject("/Subtype")] = NameObject("/Form")
    s[NameObject("/FormType")] = NumberObject(1)
    s[NameObject("/BBox")] = ArrayObject([FloatObject(x) for x in bbox])
    s[NameObject("/Matrix")] = ArrayObject([NumberObject(1), NumberObject(0),
                                            NumberObject(0), NumberObject(1),
                                            NumberObject(0), NumberObject(0)])
    s[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/Helv"): font_ref})
    })
    return writer._add_object(s)


def _set_custom_text_field(writer, field_name, text, max_size=11.0):
    """Set a text field's value and give it our own centered multi-line /AP."""
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject
    # Reuse the form's existing Helvetica (it carries /Encoding, so text renders
    # in strict viewers like Adobe; a bare font with no encoding shows blank).
    font_ref = None
    try:
        acro = writer._root_object["/AcroForm"].get_object()
        font_ref = acro["/DR"].get_object()["/Font"].get_object().raw_get("/Helv")
    except Exception:
        font_ref = None
    if font_ref is None:
        font_ref = writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }))
    for page in writer.pages:
        for annot in page.get("/Annots", []) or []:
            o = annot.get_object()
            t = o.get("/T")
            if t is None and o.get("/Parent") is not None:
                t = o.get("/Parent").get_object().get("/T")
            if str(t) != field_name:
                continue
            rect = [float(x) for x in o["/Rect"]]
            bbox = [0, 0, rect[2] - rect[0], rect[3] - rect[1]]
            q = int(o.get("/Q", 0) or 0)
            o[NameObject("/V")] = TextStringObject(text)
            ap = _text_block_appearance(writer, bbox, text, q, max_size, font_ref)
            o[NameObject("/AP")] = DictionaryObject({NameObject("/N"): ap})
            return


def fill_pdf(template_path, output_path, text_fields, check_fields):
    """Fill the template PDF and write the result.

    Uses pypdf's form-fill, which GENERATES the appearance (/AP) stream for
    each field. That makes the values visible in every PDF viewer, not just
    the ones that honor /NeedAppearances (the previous approach left some
    viewers showing the template's blank placeholders).

    A checkbox value of "P" or "E" (used for skill proficiency / expertise)
    is checked like any other box, then has its tick re-drawn as that letter.
    """
    from pypdf.generic import NameObject, BooleanObject, NumberObject, TextStringObject

    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.append(reader)

    # Long, flowing text fields are single-line and fixed at 10pt in the
    # template, so long content spills out of the box. Make them multiline and
    # auto-sizing (DA font size 0): pypdf then word-wraps and shrinks the font
    # to fit (capped at 12pt for short content).
    MULTILINE = 1 << 12
    for page in writer.pages:
        for annot in page.get("/Annots", []) or []:
            o = annot.get_object()
            t = o.get("/T")
            if t is None and o.get("/Parent") is not None:
                t = o.get("/Parent").get_object().get("/T")
            if str(t) in FLOW_TEXT_FIELDS:
                o[NameObject("/DA")] = TextStringObject("/Helv 0 Tf 0 0 0 rg")
                o[NameObject("/Ff")] = NumberObject(int(o.get("/Ff", 0) or 0) | MULTILINE)

    # Combine into one {field_name: value} map.
    #   text fields -> their string value (skip empties)
    #   checked boxes -> their "on" appearance state ("/Yes" on this template)
    values = {}
    custom = {}   # fields we render ourselves (CUSTOM_TEXT_FIELDS)
    for name, val in text_fields.items():
        if val in (None, ""):
            continue
        if name in CUSTOM_TEXT_FIELDS:
            custom[name] = val
        else:
            values[name] = val
    markers = {}  # field name -> "P"/"E" (letter) or "dot" (filled star)
    for name, on in check_fields.items():
        if on:
            values[name] = "/Yes"
            markers[name] = on if on in ("P", "E") else "dot"

    # Fields are spread across both pages; update_page_form_field_values only
    # touches fields present on the given page, so call it for each page.
    for page in writer.pages:
        writer.update_page_form_field_values(page, values, auto_regenerate=False)

    # Re-draw every ticked box: P/E letters on the proficiency dots, and a
    # solid filled star (matching the outline) on the rest — so the whole
    # diamond/star is filled in rather than half-filled.
    if markers:
        _apply_marker_appearances(writer, markers)

    # Fields we lay out ourselves (SPEED two lines, big centered HP numbers).
    for name, val in custom.items():
        _set_custom_text_field(writer, name, val, CUSTOM_TEXT_FIELDS[name])

    # Appearances are now baked in, so readers don't need to regenerate them.
    acroform = writer._root_object.get("/AcroForm")
    if acroform is not None:
        acroform = acroform.get_object()  # resolve indirect reference
        acroform[NameObject("/NeedAppearances")] = BooleanObject(False)

    # Flatten the form so the result renders IDENTICALLY in every viewer.
    # Interactive readers (Edge, Firefox/PDF.js, ...) otherwise re-render form
    # fields from /V + /DA and ignore our custom appearances; flattening bakes
    # everything into static page content. Done in memory to avoid file locks.
    import io
    buf = io.BytesIO()
    writer.write(buf)
    data = _flatten_bytes(buf.getvalue())
    with open(output_path, "wb") as f:
        f.write(data)


def _flatten_bytes(data):
    """Return PDF bytes with form fields + annotations baked into static page
    content (via PyMuPDF). Returns the input unchanged if PyMuPDF is missing —
    the un-flattened file still works in appearance-honoring viewers like Adobe."""
    try:
        import fitz
    except ImportError:
        return data
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        doc.bake(widgets=True, annots=True)
    except TypeError:
        doc.bake()
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out


def main():
    script_dir = Path(__file__).parent.resolve()
    chars_dir = script_dir / "characters"
    output_dir = script_dir / "output"
    template_path = script_dir / "_character_sheet_template.pdf"

    if not template_path.exists():
        print("ERROR: Template not found at {}".format(template_path))
        sys.exit(1)

    if not chars_dir.exists():
        print("ERROR: No characters/ directory found. Create JSON files there first.")
        sys.exit(1)

    output_dir.mkdir(exist_ok=True)

    # Optional CLI arg: generate only the named character(s) (case-insensitive,
    # matches file stem or the "name" field).
    wanted = [a.lower() for a in sys.argv[1:]]

    json_files = sorted(chars_dir.glob("*.json"))
    if not json_files:
        print("No JSON files found in {}".format(chars_dir))
        sys.exit(1)

    print("D&D 2024 Character Sheet Generator")
    print("=" * 40)
    print("Template: {}".format(template_path.name))

    processed = 0
    for jf in json_files:
        if wanted and jf.stem.lower() not in wanted:
            continue
        print("Processing {}...".format(jf.name), end=" ")
        try:
            with open(jf, "r", encoding="utf-8") as f:
                char = json.load(f)

            if wanted and char.get("name", "").lower() not in wanted \
                    and jf.stem.lower() not in wanted:
                continue

            name = char.get("name", jf.stem)
            warnings = validate_character(char)
            text_fields, check_fields = compute_fields(char)

            out_name = "{}.pdf".format(jf.stem)
            out_path = output_dir / out_name
            fill_pdf(str(template_path), str(out_path), text_fields, check_fields)

            print("-> {}".format(out_path.name))
            for w in warnings:
                print("    ! {}".format(w))
            processed += 1
        except Exception as e:
            print("ERROR: {}".format(e))

    if wanted and processed == 0:
        print("\nNo character matched: {}".format(", ".join(sys.argv[1:])))
        print("Available: {}".format(", ".join(j.stem for j in json_files)))

    print()
    print("Done! {} sheet(s) written to: {}".format(processed, output_dir))


if __name__ == "__main__":
    main()

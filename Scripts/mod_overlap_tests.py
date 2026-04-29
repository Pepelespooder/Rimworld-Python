import os
import xml.etree.ElementTree as ET

REPORT_NAME = "mod_overlap_report.txt"

PATCH_RISK = {
    "PatchOperationReplace": "check",
    "PatchOperationRemove": "check",
    "PatchOperationSequence": "review",
    "PatchOperationAdd": "review",
    "PatchOperationInsert": "review",
    "PatchOperationAttributeSet": "review",
    "PatchOperationAddModExtension": "note",
    "PatchOperationConditional": "note",
    "PatchOperationFindMod": "note",
}

def lower(value):
    return (value or "").lower()

def clean(value):
    return (value or "").strip()

def safe_text(node):
    if node is None or node.text is None:
        return ""
    return node.text.strip()

def bool_attr(node, name):
    return lower(node.attrib.get(name, "")) == "true"

def official_mod(mod):
    return mod.isCoreMod or mod.isOfficialMod or lower(mod.packageId).startswith("ludeon.")

def walk_xml_files(root_dir):
    for subdir in ["About", "Defs", "Patches"]:
        base = os.path.join(root_dir, subdir)
        if not os.path.isdir(base):
            continue
        for current, dirs, files in os.walk(base):
            for file_name in files:
                if file_name.lower().endswith(".xml"):
                    yield os.path.join(current, file_name)

def parse_xml(path, problems):
    try:
        return ET.parse(path)
    except Exception as exc:
        problems.append("XML parse failed: " + path + " :: " + str(exc))
        return None

def bucket_add(bucket, key, item):
    if key not in bucket:
        bucket[key] = []
    bucket[key].append(item)

def normalize_xpath(xpath):
    return " ".join(clean(xpath).replace('"', "'").split())

def xpath_family(xpath):
    value = normalize_xpath(xpath)
    if "/" not in value:
        return value
    parts = value.split("/")
    return "/".join(parts[:min(len(parts), 4)])

def patch_class(node):
    class_name = node.attrib.get("Class", "")
    if "." in class_name:
        return class_name.split(".")[-1]
    return class_name

def patch_risk(class_name, xpath):
    name = patch_class_from_name(class_name)
    if name in PATCH_RISK:
        return PATCH_RISK[name]
    if "Defs/" in xpath or "/Defs/" in xpath:
        return "review"
    return "note"

def patch_class_from_name(class_name):
    if "." in class_name:
        return class_name.split(".")[-1]
    return class_name

def mod_label(mod):
    return mod.name + " [" + mod.packageId + "]"

def source_label(mod, rel_path):
    return mod_label(mod) + " :: " + rel_path

def display_sources(values):
    return [value["label"] for value in values]

def all_sources_official(values):
    return values and all(value["official"] for value in values)

def nonofficial_sources(values):
    return [value for value in values if not value["official"]]

mods = list(rim.active_mods())
package_ids = {}
def_names = {}
inherited_defs = {}
patch_targets = {}
patch_families = {}
patches_by_file = {}
parse_problems = []
mod_stats = {}
scanned_xml = 0

for mod in mods:
    mod_stats[mod.packageId] = {
        "name": mod.name,
        "official": official_mod(mod),
        "xml": 0,
        "defs": 0,
        "patches": 0,
        "check_patch": 0,
        "review_patch": 0,
    }

    bucket_add(package_ids, lower(mod.packageId), mod_label(mod))

    for path in walk_xml_files(mod.rootDir):
        scanned_xml += 1
        mod_stats[mod.packageId]["xml"] += 1
        tree = parse_xml(path, parse_problems)
        if tree is None:
            continue

        root = tree.getroot()
        rel_path = path.replace(mod.rootDir, "").lstrip("\\/")
        normalized_path = lower(path).replace("\\", "/")

        if "/defs/" in normalized_path:
            for node in root.iter():
                def_name = safe_text(node.find("defName"))
                if not def_name:
                    continue

                is_abstract = bool_attr(node, "Abstract")
                parent_name = clean(node.attrib.get("ParentName", ""))
                key = node.tag + ":" + def_name
                item = {
                    "official": official_mod(mod),
                    "label": source_label(mod, rel_path),
                    "abstract": is_abstract,
                    "parent": parent_name,
                    "mod": mod.packageId,
                    "node": node.tag,
                    "defName": def_name,
                }

                mod_stats[mod.packageId]["defs"] += 1
                if is_abstract:
                    bucket_add(inherited_defs, key, item)
                else:
                    bucket_add(def_names, key, item)

        if "/patches/" in normalized_path:
            for node in root.iter():
                class_name = node.attrib.get("Class", "")
                if "PatchOperation" not in class_name:
                    continue

                xpath = normalize_xpath(safe_text(node.find("xpath")))
                if not xpath:
                    continue

                risk = patch_risk(class_name, xpath)
                item = {
                    "official": official_mod(mod),
                    "label": source_label(mod, rel_path) + " :: " + class_name,
                    "risk": risk,
                    "xpath": xpath,
                    "family": xpath_family(xpath),
                    "mod": mod.packageId,
                    "class": patch_class_from_name(class_name),
                }

                mod_stats[mod.packageId]["patches"] += 1
                if risk == "check":
                    mod_stats[mod.packageId]["check_patch"] += 1
                elif risk == "review":
                    mod_stats[mod.packageId]["review_patch"] += 1

                bucket_add(patch_targets, xpath, item)
                bucket_add(patch_families, item["family"], item)
                bucket_add(patches_by_file, source_label(mod, rel_path), item)

duplicate_packages = [(key, values) for key, values in package_ids.items() if key and len(values) > 1]

all_duplicate_defs = [(key, values) for key, values in def_names.items() if len(values) > 1]
official_duplicate_defs = [(key, values) for key, values in all_duplicate_defs if all_sources_official(values)]
duplicate_defs = [(key, display_sources(values)) for key, values in all_duplicate_defs if not all_sources_official(values)]

abstract_duplicates = [(key, display_sources(values)) for key, values in inherited_defs.items() if len(values) > 1 and not all_sources_official(values)]

patch_collisions_to_check = []
patch_collisions_to_review = []
patch_collisions_to_note = []

for xpath, values in patch_targets.items():
    if len(values) < 2:
        continue
    risks = [value["risk"] for value in values]
    row = (xpath, [value["risk"] + " :: " + value["label"] for value in values])
    if "check" in risks:
        patch_collisions_to_check.append(row)
    elif "review" in risks:
        patch_collisions_to_review.append(row)
    else:
        patch_collisions_to_note.append(row)

patch_family_hotspots = []
for family, values in patch_families.items():
    mods_touching = {}
    for value in values:
        mods_touching[value["mod"]] = True
    if len(values) >= 4 and len(mods_touching) >= 2:
        labels = [value["risk"] + " :: " + value["xpath"] + " :: " + value["label"] for value in values[:12]]
        patch_family_hotspots.append((family, labels))

patch_burst_files = []
for file_label, values in patches_by_file.items():
    check_count = len([value for value in values if value["risk"] == "check"])
    if len(values) >= 20 or check_count >= 5:
        patch_burst_files.append((file_label, ["patches " + str(len(values)) + ", replace/remove " + str(check_count)]))

busy_mods = []
for package_id, stats in mod_stats.items():
    if stats["official"]:
        continue
    score = stats["check_patch"] * 4 + stats["review_patch"] * 2 + stats["patches"]
    if score >= 20 or stats["check_patch"] >= 3:
        busy_mods.append((stats["name"] + " [" + package_id + "]", [
            "xml " + str(stats["xml"]) +
            ", defs " + str(stats["defs"]) +
            ", patches " + str(stats["patches"]) +
            ", replace/remove " + str(stats["check_patch"]) +
            ", add/sequence " + str(stats["review_patch"])
        ]))

def sort_rows(rows):
    return sorted(rows, key=lambda row: len(row[1]), reverse=True)

duplicate_defs = sort_rows(duplicate_defs)
abstract_duplicates = sort_rows(abstract_duplicates)
patch_collisions_to_check = sort_rows(patch_collisions_to_check)
patch_collisions_to_review = sort_rows(patch_collisions_to_review)
patch_collisions_to_note = sort_rows(patch_collisions_to_note)
patch_family_hotspots = sort_rows(patch_family_hotspots)
patch_burst_files = sort_rows(patch_burst_files)
busy_mods = sort_rows(busy_mods)

lines = []
lines.append("Mod overlap report")
lines.append("==================")
lines.append("")
lines.append("Active mods: " + str(len(mods)))
lines.append("XML files checked: " + str(scanned_xml))
lines.append("Skipped official Core/DLC duplicate defs: " + str(len(official_duplicate_defs)))
lines.append("")
lines.append("How to read this")
lines.append("- Duplicate concrete defs are usually worth checking unless the mods are meant to replace each other.")
lines.append("- Shared patch xpaths are not automatically bad. Replace/remove operations deserve the closest look.")
lines.append("- Abstract/template duplicates are often harmless, but can still reveal copied frameworks or bundled libraries.")
lines.append("")

def add_section(title, rows, limit):
    lines.append(title + " (" + str(len(rows)) + ")")
    if not rows:
        lines.append("  none")
    for key, values in rows[:limit]:
        lines.append("  " + key)
        for value in values[:10]:
            lines.append("    - " + value)
        if len(values) > 10:
            lines.append("    - ... " + str(len(values) - 10) + " more")
    if len(rows) > limit:
        lines.append("  ... " + str(len(rows) - limit) + " more")
    lines.append("")

add_section("Duplicate package IDs", duplicate_packages, 25)
add_section("Duplicate concrete defs", duplicate_defs, 100)
add_section("Duplicate abstract/template defs", abstract_duplicates, 50)
add_section("Same xpath, includes replace/remove", patch_collisions_to_check, 100)
add_section("Same xpath, add/sequence/attribute patches", patch_collisions_to_review, 100)
add_section("Same xpath, probably informational", patch_collisions_to_note, 50)
add_section("Busy xpath areas", patch_family_hotspots, 75)
add_section("Large patch files", patch_burst_files, 50)
add_section("Patch-heavy non-official mods", busy_mods, 50)

lines.append("XML parse problems (" + str(len(parse_problems)) + ")")
if parse_problems:
    for problem in parse_problems[:100]:
        lines.append("  - " + problem)
    if len(parse_problems) > 100:
        lines.append("  - ... " + str(len(parse_problems) - 100) + " more")
else:
    lines.append("  none")

report_path = os.path.join(scripts_root, REPORT_NAME)
with open(report_path, "w") as report:
    report.write("\n".join(lines))

hard_issues = len(duplicate_packages) + len(parse_problems)
check_count = len(duplicate_defs) + len(patch_collisions_to_check)
review_count = len(abstract_duplicates) + len(patch_collisions_to_review) + len(patch_family_hotspots)
note_count = len(patch_collisions_to_note) + len(patch_burst_files) + len(busy_mods)

log("<color=#ffd166><b>Mod check:</b></color> <color=#f8f8f2>" + str(len(mods)) + " mods, " + str(scanned_xml) + " XML files.</color>")
log("<color=#ffd166><b>Mod check:</b></color> <color=#f8f8f2>package/xml errors " + str(hard_issues) + ", check " + str(check_count) + ", review " + str(review_count) + ", notes " + str(note_count) + ".</color>")
log("<color=#ffd166><b>Mod check:</b></color> <color=#66d9ef>" + report_path + "</color>")

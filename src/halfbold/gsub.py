from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.otBase import BaseTable

NO_REQUIRED_FEATURE = 0xFFFF


def has_scripted_gsub(font: TTFont) -> bool:
    if "GSUB" not in font:
        return False
    script_list = font["GSUB"].table.ScriptList
    return bool(script_list and script_list.ScriptRecord)


def prepend_lookups(original: BaseTable, addition: BaseTable, tag: str) -> BaseTable:
    added = addition.LookupList.Lookup
    shift_indices(original, "LookupListIndex", len(added))
    original.LookupList.Lookup[0:0] = added
    feature_indices = addition.FeatureList.FeatureRecord[0].Feature.LookupListIndex
    add_feature_to_every_langsys(original, tag, feature_indices)
    sort_feature_records(original)
    return original


def add_feature_to_every_langsys(
    gsub: BaseTable, tag: str, lookup_indices: list[int]
) -> None:
    records = gsub.FeatureList.FeatureRecord
    extended: set[int] = set()
    new_index: int | None = None
    for langsys in every_langsys(gsub):
        existing = [i for i in langsys.FeatureIndex if records[i].FeatureTag == tag]
        if existing:
            feature = records[existing[0]].Feature
            if id(feature) not in extended:
                feature.LookupListIndex.extend(lookup_indices)
                extended.add(id(feature))
            continue
        if new_index is None:
            new_index = len(records)
            records.append(feature_record(tag, lookup_indices))
        langsys.FeatureIndex.append(new_index)


def every_langsys(gsub: BaseTable) -> list[BaseTable]:
    found = []
    for script_record in gsub.ScriptList.ScriptRecord:
        script = script_record.Script
        if script.DefaultLangSys is not None:
            found.append(script.DefaultLangSys)
        found.extend(record.LangSys for record in script.LangSysRecord)
    return found


def feature_record(tag: str, lookup_indices: list[int]) -> BaseTable:
    record = otTables.FeatureRecord()
    record.FeatureTag = tag
    record.Feature = otTables.Feature()
    record.Feature.FeatureParams = None
    record.Feature.LookupListIndex = list(lookup_indices)
    return record


def sort_feature_records(gsub: BaseTable) -> None:
    records = gsub.FeatureList.FeatureRecord
    order = sorted(range(len(records)), key=lambda i: records[i].FeatureTag)
    remap = {old: new for new, old in enumerate(order)}
    gsub.FeatureList.FeatureRecord = [records[i] for i in order]
    for langsys in every_langsys(gsub):
        langsys.FeatureIndex = [remap[i] for i in langsys.FeatureIndex]
        if langsys.ReqFeatureIndex != NO_REQUIRED_FEATURE:
            langsys.ReqFeatureIndex = remap[langsys.ReqFeatureIndex]
    variations = getattr(gsub, "FeatureVariations", None)
    if variations is not None:
        for variation in variations.FeatureVariationRecord:
            for sub in variation.FeatureTableSubstitution.SubstitutionRecord:
                sub.FeatureIndex = remap[sub.FeatureIndex]


def shift_indices(table: BaseTable, attribute: str, offset: int) -> None:
    seen: set[int] = set()
    stack: list[object] = [table]
    while stack:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        if isinstance(obj, list | tuple):
            stack.extend(obj)
        elif isinstance(obj, dict):
            stack.extend(obj.values())
        elif isinstance(obj, BaseTable):
            value = getattr(obj, attribute, None)
            if isinstance(value, list):
                setattr(obj, attribute, [i + offset for i in value])
            elif isinstance(value, int):
                setattr(obj, attribute, value + offset)
            stack.extend(vars(obj).values())

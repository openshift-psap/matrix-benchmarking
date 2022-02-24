import types, datetime
import yaml
import os, pathlib

import common
import store

import xml.etree.ElementTree as ET

def _parse_generated(fname, elt):
    for key in "Title", "TestClient", "Description":
        value = elt.find(key).text
        print(f"{key}: {value}")


def _parse_system(fname, elt):
    for key in "Identifier", "Hardware", "Software":
        value = elt.find(key).text
        print(f"{key}: {value}")

def _duplicated_entry(import_key, old_location, new_location):
    print(f"WARNING: duplicated results key: {import_key}")
    print(f"WARNING:   old:")
    print(ET.tostring(old_location).decode("ascii"))
    print(f"WARNING:   new: {new_location}")
    print(ET.tostring(new_location).decode("ascii"))
    import pdb;pdb.set_trace()
    pass

def _parse_result(fname, elt):
    results = types.SimpleNamespace()

    for key in "Identifier", "Title", "AppVersion", "Arguments", \
        "Description", "Scale", "Proportion", "DisplayFormat":
        if elt.find(key) is None:
            results.__dict__[key] = "missing"
        elif not elt.find(key).text:
            results.__dict__[key] = "N/A"
        else:
            results.__dict__[key] = elt.find(key).text


    for key in "Identifier", "Value", "RawString":
        results.__dict__[f"Data_{key}"]  = elt.find("Data").find("Entry").find(key).text

    if results.Data_Value is None:
        print(elt.find("Data").find("Entry").find("JSON").text)
        return

    results.Data_Value = float(results.Data_Value)

    entry_import_settings = {
        "system": fname.replace(".xml", ""),
        "title": results.Title,
        "version": results.AppVersion,
        "argument": results.Arguments,
        "id": results.Identifier,
        "repeat": 0,
    }

    if not entry_import_settings["version"]: import pdb;pdb.set_trace()
    for i in range(0, 10):
        import_key = common.Matrix.settings_to_key(entry_import_settings)
        if import_key not in common.Matrix.import_map:
            break
        entry_import_settings["repeat"] += 1
    else:
        raise RuntimeError("Found 10 duplicated results. Is that correct?")

    store.add_to_matrix(entry_import_settings, elt, results, _duplicated_entry)

def _parse_unknown(elt):
    import pdb;pdb.set_trace()
    pass

PARSERS = {
    "Generated": _parse_generated,
    "System": _parse_system,
    "Result": _parse_result
}

def parse_data(results_dir):

    path = os.walk(results_dir)

    for this_dir, directories, files in path:
        for fname in files:
            root = ET.parse(pathlib.Path(this_dir) / fname).getroot()
            for elt in root:
                PARSERS.get(elt.tag, _parse_unknown)(fname, elt)
                pass

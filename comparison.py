import itertools
from pprint import pprint
import re
import json
import html
import sys
from import_util import multidict_add, get_lang_prio
from collections import UserString

def widetermname(termpost):
    return ",".join(termpost["slugs"])

def group(l, key):
    d = {}
    for e in l:
        v = str(e["slugs"][0])
        d.setdefault(v, []).append(e)
    return d

def json_key(e):
    return json.dumps(e, sort_keys = True)

term_prio = {
    "TE":0,
    "SYTE":1,
    "AVTE":2,
}

def term_sortkey(term):
    return (get_lang_prio(term["lang"]), term_prio.get(term["status"], 100))

def get_added_removed(l1, l2):
    added = [e for e in l2 if e not in l1]
    removed = [e for e in l1 if e not in l2]
    return (added, removed)

def json_repr(o):
    return json.dumps(o, sort_keys=True)

def compare_termposts(title, post1, post2):
    diff = []
    for e1, e2 in itertools.zip_longest(post1, post2):
        if e1 == None:
            diff.append({"action":"added", "title": title, "added_id": e2["id"], "added": [{"key": k, "value": e2[k]} for k in sorted(set(e2.keys()) - set(["id", "kalla"]))]})
            return diff # XXX too early
        if e2 == None:
            diff.append({"action":"removed", "title": title, "removed_id": e1["id"], "removed": [{"key": k, "value": e1[k]} for k in sorted(set(e1.keys()) - set(["id", "kalla"]))]})
            return diff # XXX too early
        e1_id = e1["slugs"][0]
        e2_id = e2["slugs"][0]
        e1_kalla = e1["kalla"]
        e2_kalla = e2["kalla"]
#        del e1["id"]
#        del e2["id"]
        for ignore_key in ["kalla", "gitversion"]:
            if ignore_key in e1:
                del e1[ignore_key]
            if ignore_key in e2:
                del e2[ignore_key]
        if e1 != e2:
            added = []
            removed = []
            changed = []
            keys1 = set(e1.keys()) - set(["INID", "internal_comment"])
            keys2 = set(e2.keys()) - set(["INID", "internal_comment"])
            removed.extend([{"key":k, "value": e1[k]} for k in sorted(keys1 - keys2)])
            added.extend([{"key":k, "value": e2[k]} for k in sorted(keys2 - keys1)])
            for key in sorted(keys1 & keys2):
                if key in ["onlysearch"] or key.endswith("SYTE"):
                    if sorted(e1[key], key=json_repr) != sorted(e2[key], key=json_repr):
                        changed.append({"key": key, "removed": e1[key], "added": e2[key]})
                elif key == "ILLU":
                    illuobjects1 = [e.copy() for e in e1[key]]
                    illuobjects2 = [e.copy() for e in e2[key]]
                    if sorted(illuobjects1, key=json_repr) != sorted(illuobjects2, key=json_repr):
                        changed.append({"key": key, "removed": e1[key], "added": e2[key]})
                elif key in ["seealso", "seeunder"]:
                    if sorted(e1[key], key=json_repr) != sorted(e2[key], key=json_repr):
                        changed.append({"key": key, "removed": e1[key], "added": e2[key]})
                elif key in ["terms"]:
                    termobjects1 = sorted(e1[key], key=term_sortkey)
                    termobjects2 = sorted(e2[key], key=term_sortkey)
                    termobjects1_filtered = [e for e in termobjects1 if e not in termobjects2]
                    termobjects2_filtered = [e for e in termobjects2 if e not in termobjects1]
                    termobjects1 = termobjects1_filtered
                    termobjects2 = termobjects2_filtered
                    for termobject1, termobject2 in itertools.zip_longest(termobjects1, termobjects2):
                        if termobject1 is None:
                            added.append({"key": key, "value": termobject2})
                            continue
                        if termobject2 is None:
                            removed.append({"key": key, "value": termobject1})
                            continue

                        if sorted(termobject1.items(), key=json_repr) != sorted(termobject2.items(), key=json_repr):
                            changed.append({"key": key, "removed": termobject1, "added": termobject2})
                elif key in ["classifications"]:
                    if sorted(e1[key], key=json_repr) != sorted(e2[key], key=json_repr):
                        changed.append({"key": key, "removed": e1[key], "added": e2[key]})
                elif key in ["texts"]:
                    subtypes1 = set([e["type"] for e in e1[key]])
                    subtypes2 = set([e["type"] for e in e2[key]])
                    for subtype in sorted(subtypes1 - subtypes2):
                        for e in e1[key]:
                            if e["type"] == subtype:
                                removed.append({"key":key + " " + subtype, "value": e})
                    for subtype in sorted(subtypes2 - subtypes1):
                        for e in e2[key]:
                            if e["type"] == subtype:
                                added.append({"key":key + " " + subtype, "value": e})

                    for subtype in sorted(subtypes1 & subtypes2):
                        (termobjects_added, termobjects_removed) = get_added_removed([e for e in e1[key] if e["type"] == subtype],
                                                                                     [e for e in e2[key] if e["type"] == subtype])
                        if termobjects_removed and termobjects_added:
                            changed.append({"key": key + " " + subtype, "removed": termobjects_removed, "added": termobjects_added})
                        elif termobjects_removed:
                            removed.append({"key": key + " " + subtype, "value": termobjects_removed}) 
                        elif termobjects_added:
                            added.append({"key": key + " " + subtype, "value": termobjects_added})
                            
                            
                elif key == "searchterms":
                    if sorted(e1[key]) != sorted(e2[key]):
                        changed.append({"key": key, "removed": e1[key], "added": e2[key]})
                elif key in ["internal_comment", "fulltextsearch"]:
                    pass
                else:
                    if e1[key] != e2[key]:
                        changed.append({"key": key, "removed": e1[key], "added": e2[key]})
            mostprio_term = sorted(post1[0]["terms"], key=term_sortkey)[0]
            if added or removed or changed:
                diff.append({
                    "action": "diff",
                    "title": title,
                    "shorttitle": mostprio_term.get("term", ""),
                    "added_id": e2_id,
                    "removed_id": e1_id,
                    "added": added,
                    "removed": removed,
                    "changed": changed,
                    })
    return diff

def add_dict_nonempty(d, k, v):
    if v:
        d[k] = v

def rstrip_string(o):
    if isinstance(o, str):
        return o.rstrip()
    return o

ignored_changed_metadata = set()

def compare_sources(rtb_bef_kalla, rtb_kalla, rtb_all_termposts, rtb_bef_all_termposts):

    rtb_bef_termposts = group(rtb_bef_all_termposts[rtb_bef_kalla["id"]], "terms")
    rtb_termposts = group(rtb_all_termposts[rtb_kalla["id"]], "terms")

    rtb_bef_kalla_keys = set(rtb_bef_kalla.keys()) - set(["errors", "gitversion"])
    rtb_kalla_keys = set(rtb_kalla.keys()) - set(["errors", "gitversion"])

    source_diff = {}
    
    add_dict_nonempty(source_diff, "removed_metadata", [{"key": key, "value": rtb_bef_kalla[key]} for key in sorted(rtb_bef_kalla_keys - rtb_kalla_keys)])
    add_dict_nonempty(source_diff, "added_metadata", [{"key": key, "value": rtb_kalla[key]} for key in sorted(rtb_kalla_keys - rtb_bef_kalla_keys)])

    changed_metadata = []
    for key in sorted((rtb_kalla_keys & rtb_bef_kalla_keys) - ignored_changed_metadata):
        bef_values = rstrip_string(rtb_bef_kalla[key])
        values = rstrip_string(rtb_kalla[key])
        if bef_values != values:
            changed_metadata.append({"key": key, "removed": bef_values, "added": values})
    add_dict_nonempty(source_diff, "changed_metadata", changed_metadata)

    rtb_bef_termposts_keys = set(rtb_bef_termposts.keys())
    rtb_termposts_keys = set(rtb_termposts.keys())

    add_dict_nonempty(source_diff, "removed_terms", sorted([widetermname(rtb_bef_termposts[e][0]) for e in rtb_bef_termposts_keys - rtb_termposts_keys]))
    add_dict_nonempty(source_diff, "added_terms", sorted([widetermname(rtb_termposts[e][0]) for e in rtb_termposts_keys - rtb_bef_termposts_keys]))

    termpost_diffs = []
    for key in sorted(rtb_termposts_keys & rtb_bef_termposts_keys, key=lambda x: widetermname(rtb_bef_termposts[x][0])):
        termpost_bef = rtb_bef_termposts[key]
        termpost = rtb_termposts[key]
        if termpost_bef != termpost:
            diffs = compare_termposts(widetermname(termpost_bef[0]), termpost_bef, termpost)
            if diffs:
                termpost_diffs.append(diffs)

    add_dict_nonempty(source_diff, "changed_terms", termpost_diffs)
    return source_diff

import collections

def translate_status(status):
    if status == 2:
        return "publicerad"
    elif status == 1:
        return "avpublicerad"
    elif status == 0:
        return "inteFärdig"
    else:
        return "felaktigstatus"

def compare(db_prod, db_staging):
    import_status = db_staging.status.find_one({"key":"import"})
    if not import_status:
        return None
    imported_gitversion = import_status["gitversion"]
    imported_nsources = import_status["nsources"]
    sources = list(db_staging.kalla.find({}, {"_id": False}))
    sources_prod = {source["id"]:source for source in db_prod.kalla.find({}, {"_id": False})}
    rtb_all_termposts = collections.defaultdict(list)
    for e in db_staging.termpost.find({}, {"_id": False}):
        if e["gitversion"] != imported_gitversion:
            return None
        rtb_all_termposts[e["kalla"]["id"]].append(e)
    rtb_prod_all_termposts = collections.defaultdict(list)
    for e in db_prod.termpost.find({}, {"_id": False}):
        rtb_prod_all_termposts[e["kalla"]["id"]].append(e)

    if imported_nsources != len(sources):
        return None
    for source in sources:
        if source["gitversion"] != imported_gitversion:
            return None
        if len(rtb_all_termposts.get(source["id"], [])) == 0:
            return None

    only_tolka_changes = []
    no_changes = {}
    sources_ids = set([source["id"] for source in sources])
    source_filenames = {}
    source_diffs = []
    other_errors = []
    for source in sources:
        source_prod = sources_prod.get(source["id"])
        if source_prod:
            source_prod["status"] = translate_status(source_prod.get("status", 2))
        source["status"] = translate_status(source.get("status", 2))
        source_filenames[source["id"]] = source["filename"]
        errors = [" ".join(error) for error in source.get("errors", [])]
        if source_prod is None:
            source_diff = compare_sources(source, source, rtb_all_termposts, rtb_prod_all_termposts)
        else:
            source_diff = compare_sources(source_prod, source, rtb_all_termposts, rtb_prod_all_termposts)
        if source_diff:
            source_diffs.append((source["id"], source["filename"], source_diff, errors))
        elif errors:
            other_errors.append((source["id"], source["filename"], errors))

    # for source_id in sorted(different_terms_sources):
    #     source = source_diffs_by_id[source_id]
    #     print("<li><a href='#%d'>Källa %d (%s)</a>" % (source_id, source_id, source_filenames[source_id]))
    #     added_terms = source.get("added_terms", [])
    #     removed_terms = source.get("removed_terms", [])
    #     print("<ul>")
    #     terms = rtb_all_termposts[source_id]
    #     bef_terms = rtb_bef_all_termposts[source_id]
    #     if added_terms:
    #         print("<li>bara i textfil:", len(added_terms), "av", len(terms))
    #     if removed_terms:
    #         print("<li>bara i SQL:", len(removed_terms), "av", len(bef_terms))
    #     print("</ul>")
    # print("</ul>")


    
    return source_diffs, other_errors, imported_gitversion

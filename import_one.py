import re
import json
from import_util import tag_tree, named_tag_tree, rename_dict, sort_terms, split_searchterm, multidict_add, unique, decode_entities, textconvert_annotated_term, embeddedconvert_annotated_term, textconvert_annotated_text
import traceback
import threading
threadlocal = threading.local()
threadlocal.logging = []
import sys
from slug import get_slugs
import os.path

def log(*s):
    threadlocal.logging.append([str(e) for e in s])

def getlog():
    return threadlocal.logging.copy()

def clearlog():
    threadlocal.logging.clear()

top_level = [
    "EKVI",
    "FO",
    "ILLU",
    "IL",
    "INAN",
    "INID",
    "KL",
    "KLAR",
    "LOGG",
    "RIAN",
    "RIFR",
    "TI",
]

top_level_lang = [
    "AN",
    "AVTE",
    "AVNA",
    "AVPH",
    "BT",
    "DF",
    "EKVI",
    "EX",
    "FK",
    "INNA",
    "INTE",
    "KLAR",
    "KT",
    "NA",
    "NB",
    "PH",
    "RETE",
    "SA",
    "SU",
    "SYNA",
    "SYPH",
    "SYTE",
    "TE",
    "UPTE",
    "TI",
]

sub_level = [
    "BNGR",
    "ETYM",
    "FRKT",
    "GE",
    "GR",
    "GNGR",
    "HONR",
    "ILLT",
    "ILTY",
    "OKGR",
    "RF",
    "SA",
    "UT",
]

def split_key(key):
    if key[0:2].islower() and key[2:].isupper():
        lang = key[0:2]
        fieldname = key[2:]
        return (lang, fieldname)
    elif key.isupper():
        return (None, key)
    else:
        log("Ogiltigt fältnamn:", repr(key))
        #sys.exit(1)
        return (None, None)

def entry_generator(f):
    entry = []
    for row in f:
        row = row.rstrip()
        row = row.lstrip("\ufeff")
        if row and row[0] in " \t":
            if entry:
                entry[-1] += "\u2029" + row.lstrip(" \t")
            else:
                # XXX bug compatibility
                log("Första raden börjar med mellanslag:", repr(row))
                entry.append(row.lstrip())
        elif row:
            entry.append(row)
        else:
            #print(entry)
            if entry:
                yield entry
            entry = []
    if entry:
        yield entry

def parse_header_entry(rows):
    entry = {}
    for row in rows:
        (key, _, value) = row.partition(" ")
        entry[key.rstrip("\r\n").lstrip("\ufeff")] = value.rstrip("\r\n")
    return entry

split_row_re = re.compile(r"^(\S+)\s+(.*)$")

def field_generator(rows):
    current_value = None
    current_lang = None
    current_fieldname = None
    for row in rows:
        m = split_row_re.match(row)
        if m:
            key = m.group(1)
            value = m.group(2)
        else:
            key = row
            value = None
        (lang, fieldname) = split_key(key)
        if fieldname == None:
            # XXX bug compatibility
            log("Hittar inget fältnamn, tolkar som fortsättningsrad:", row)
            if not current_value:
                return
            current_value += "\u2029" + row.lstrip(" \t")
            continue            
        if current_value != None:
            yield (current_value, current_lang, current_fieldname)
        current_value = value
        current_lang = lang
        current_fieldname = fieldname
    if current_value != None:
        yield (current_value, current_lang, current_fieldname)


angle_bracket_tag_valid_re = re.compile(r"^[A-Z]")
        
def convert_tree(s, in_tree, nonembedded_pos=0, limit=None):
    tree = []
    if limit == None:
        limit = len(s)
    for start_pos, end_pos, subtree in in_tree:
        field = s[start_pos+1:end_pos]
        value_start = s.find(" ", start_pos+1, end_pos)
        #print("convert_tree", s, in_tree, nonembedded_pos, limit, value_start, start_pos, end_pos)
        if value_start >= 0:
            key = s[start_pos+1:value_start]
            if not angle_bracket_tag_valid_re.match(key):
                if tree and tree[-1][0] == "text":
                    tree[-1] = ("text", tree[-1][1] + s[nonembedded_pos:end_pos+1])
                else:
                    tree.append(("text", s[nonembedded_pos:end_pos+1]))
                nonembedded_pos = end_pos + 1
                continue
            if nonembedded_pos != start_pos:
                if tree and tree[-1][0] == "text":
                    tree[-1] = ("text", tree[-1][1] + s[nonembedded_pos:start_pos])
                else:
                    tree.append(("text", s[nonembedded_pos:start_pos]))
            tree.append(("tag", key, convert_tree(s, subtree, value_start+1, limit=end_pos)))
            nonembedded_pos = end_pos + 1
        else:
            if tree and tree[-1][0] == "text":
                tree[-1] = ("text", tree[-1][1] + s[nonembedded_pos:end_pos+1])
            else:
                tree.append(("text", s[nonembedded_pos:end_pos+1]))
            nonembedded_pos = end_pos + 1
    if nonembedded_pos != limit:
        if tree and tree[-1][0] == "text":
            tree[-1] = ("text", tree[-1][1] + s[nonembedded_pos:limit])
        else:
            tree.append(("text", s[nonembedded_pos:limit]))
    return tree

def parse_embedded(s):
    tree = tag_tree(s, "<", ">", log=log)
    converted = convert_tree(s, tree)
    embedded = []
    nonembedded = ""
    nonembedded_pos = 0
    for start_pos, end_pos, subtree in tree:
        field = s[start_pos+1:end_pos]
        (key, _, value) = field.partition(" ")
        embedded.append((key, value, start_pos, end_pos))
        nonembedded += s[nonembedded_pos:start_pos].rstrip()
        nonembedded_pos = end_pos + 1
    nonembedded += s[nonembedded_pos:]
    return (nonembedded, embedded, converted)

#def valid_fieldname(fieldname):

def parse_entry(rows, metapost_entry):
    entry = {}
    current_field = None
    for value, lang, fieldname in field_generator(rows):
        #print(key, lang, fieldname)
        if lang == None:
            key = fieldname
        else:
            key = lang + fieldname
        if fieldname in top_level and not lang:
            if current_field != None:
                multidict_add(entry, parse_field(current_field, metapost_entry))
                current_field = None
            current_field = (key, value, fieldname, [], lang)
        elif fieldname in top_level_lang and lang:
            if current_field != None:
                multidict_add(entry, parse_field(current_field, metapost_entry))
                current_field = None
            current_field = (key, value, fieldname, [], lang)
        elif fieldname in sub_level:
            if current_field is None:
                # XXX bug compatibility
                log("Kopplat fält utan toppnivå- eller språkfält, ignorerar:", fieldname, value)
                continue
            (super_key, super_value, super_fieldname, super_subordinate, super_lang) = current_field
            super_subordinate.append((fieldname, value))
        else:
            # XXX bug compatibility
            if current_field is None:
                log("Ogiltigt fältnamn:", fieldname, value, key)
                continue
            log("Ogiltigt fältnamn, tolkar som fortsättningsrad:", fieldname, value, key)
            (c_key, c_value, c_fieldname, c_subordinate, c_lang) = current_field
            if isinstance(c_value, dict) and "value" in c_value:
                c_value["value"] += "\u2029" + value
            if isinstance(c_value, str):
                current_field = (c_key, c_value + "\u2029" + key + " " + value, c_fieldname, c_subordinate, c_lang)
    if current_field != None:
        multidict_add(entry, parse_field(current_field, metapost_entry))
    if "terms" in entry:
        entry["terms"] = sort_terms(entry["terms"])
    if "searchterms" in entry:
        entry["searchterms"] = sorted(set(entry["searchterms"]))
    if "fulltextsearch" in entry:
        if "searchterms" in entry:
            entry["fulltextsearch"] = sorted(set(entry["searchterms"]) | set(entry["fulltextsearch"]))
        else:
            entry["fulltextsearch"] = sorted(set(entry["fulltextsearch"]))
    return entry

def split_embedded_converted(tree, separator):
    #print("split_embedded", repr(s), embedded_fields, repr(separator))
    result = []
    for e in tree:
        if e[0] == "text":
            value = e[1]
            parts = value.split(separator)
            #positions = find_all(s, separator)
            #for position in positions:
            #print("parts", parts)
            if result:
                lastresult = result[-1]
                result[-1] = (lastresult[0] + parts[0], lastresult[1])
                parts = parts[1:]
            for part in parts:
                if part:
                    result.append((part, []))
        elif e[0] == "tag":
            tagname = e[1]
            subtree = e[2]
            assert(len(subtree) == 1)
            node = subtree[0]
            assert(node[0] == "text")
            if result:
                lastresult = result[-1]
                result[-1] = (lastresult[0], lastresult[1] + [(tagname, node[1])])
            else:
                result.append("", [(tagname, node[1])])
        else:
            assert(False)
    return result

reference_with_homonym_number_re = re.compile(r"^(.+) \((\d+)\)$")

def pack_RETE(s, embedded, lang):
    s = s.strip()
    m = reference_with_homonym_number_re.match(s)
    if m:
        result = {"term": string_substitutions(m.group(1)), "homonym": int(m.group(2))}
    else:
        result = {"term": string_substitutions(s)}
    for key, value in embedded:
        if key == "HONR":
            result["homonym"] = int(value)
        else:
            log("Oimplementerat kopplat fält för RETE/SU:", k)
            result[key] = value
    result["lang"] = lang
    return result

def lookup_entity(m):
    return chr(int(m.group(1), 16))

def string_substitutions(s):
    s = s.strip(" \t")
    s = decode_entities(s)
    return s

pl_och_koll = re.compile(r"^(.+) pl\.? och koll\.? (.+)$")
pl_och_koll_sep = re.compile(r"^(.+) pl\.? (.+) koll\.? (.+)$")
koll_pl_only = re.compile(r"^koll\. pl\.$")
normal_inflection = re.compile(r"^([^, ]+),? (?:pl\.? )?(.+)$")
normal_inflection_with_koll = re.compile(r"^([^, ]+),? (?:pl\. )?(.+) koll\.? (.+)$")
eller_in_second_clause = re.compile(r"^([^, ]+),? ([^ ]+) eller ([^ ]+)$")
eller_defneu_inflection = re.compile(r"^([^, ]+) ([^, ]+) eller ([^, ]+) ([^, ]+)$")
eller_twice_pl = re.compile(r"^([^, ]+) eller ([^, ]+) pl\.? ([^, ]+) eller ([^, ]+)$")
pl_only = re.compile(r"^pl\.? (.+)$")


def parse_inflection(inflection):
    m = koll_pl_only.match(inflection)
    if m:
#        log("inflection", repr(inflection), "koll_pl_only")
        return []
    m = pl_och_koll.match(inflection)
    if m:
#        log("inflection", repr(inflection), "pl_och_koll", repr((m.group(1), m.group(2))))
        return [{"definite_or_neuter": m.group(1), "plural": m.group(2), "collective": m.group(2)}]
    m = pl_och_koll_sep.match(inflection)
    if m:
#        log("inflection", repr(inflection), "pl_och_koll_sep", repr((m.group(1), m.group(2), m.group(3))))
        return [{"definite_or_neuter": m.group(1), "plural": m.group(2), "collective": m.group(3)}]
    m = normal_inflection_with_koll.match(inflection)
    if m:
#        log("inflection", repr(inflection), "normal_inflection_with_koll", repr((m.group(1), m.group(2), m.group(3))))
        return [{"definite_or_neuter": m.group(1), "plural": m.group(2), "collective": m.group(3)}]
    m = eller_in_second_clause.match(inflection)
    if m:
#        log("inflection", repr(inflection), "eller_in_second_clause", repr((m.group(1), m.group(2), m.group(3))))
        return [{"definite_or_neuter": m.group(1), "plural": m.group(2)}, {"definite_or_neuter": m.group(1), "plural": m.group(3)}]
    m = pl_only.match(inflection)
    if m:
#        log("inflection", repr(inflection), "pl_only", repr((m.group(1))))
        return [{"plural": m.group(1)}]
    m = eller_twice_pl.match(inflection)
    if m:
#        log("inflection", repr(inflection), "eller_twice_pl", repr((m.group(1), m.group(2), m.group(3), m.group(4))))
        return [{"definite_or_neuter": m.group(1), "plural": m.group(3)}, {"definite_or_neuter": m.group(2), "plural": m.group(4)}]
    m = eller_defneu_inflection.match(inflection)
    if m:
#        log("inflection", repr(inflection), "eller_defneu_inflection", repr((m.group(1), m.group(2), m.group(3), m.group(4))))
        return [{"definite_or_neuter": m.group(1), "plural": m.group(2)}, {"definite_or_neuter": m.group(3), "plural": m.group(4)}]
    m = normal_inflection.match(inflection)
    if m:
#        log("inflection", repr(inflection), "normal_inflection", repr((m.group(1), m.group(2))))
        return [{"definite_or_neuter": m.group(1), "plural": m.group(2)}]
    
    #log("inflection", repr(inflection), "fallthrough")
    definite_or_neuter, _, plural = inflection.partition(" ")
    if not definite_or_neuter:
        definite_or_neuter = None
    if not plural:
        plural = None
    return [{"definite_or_neuter": definite_or_neuter, "plural": plural}]

def splitPreferredAdmitted(metadata, lang):
    value = metadata.get("Tolka_skillnadTermSynonym_" + lang, metadata.get("Tolka_skillnadTermSynonym_förvalt", "troligenUppdelat"))
    if value == "troligenIngenSkillnad":
        return False
    elif value == "troligenUppdelat":
        return True
    else:
        return False # XXX report error

def format_tree(in_tree):
    tree = []
    for e in in_tree:
        if e[0] == "tag":
            tree.append({"tag": e[1], "content": format_tree(e[2])})
        elif e[0] == "text":
            tree.extend(named_tag_tree(decode_entities(e[1]), "{", "}", log=log))
        else:
            assert(False)
    return tree

def handle_rcon_reference(in_tree):
    assert(in_tree[0].keys() == set(["text"]))
    result = {"term": in_tree[0]["text"].rstrip(" ")}
    if len(in_tree) == 1:
        return result
    assert(len(in_tree) == 2 and in_tree[1].get("tag") == "HONR")
    assert(len(in_tree[1]["content"]) == 1)
    assert(in_tree[1]["content"][0].keys() == set(["text"]))
    result["homonym"] = in_tree[1]["content"][0]["text"]
    return result

def handle_rcon(in_tree):
    tree = []
    for e in in_tree:
        if e.get("tag") == "RCON":
            tree.append({"term": handle_rcon_reference(e["content"])})
        elif "tag" in e:
            tree.append({"tag":e["tag"], "content": handle_rcon(e["content"])})
        else:
            tree.append(e)
    return tree

def bug_compat_render_term(tree):
    s = ""
    for e in tree:
        if e[0] == "tag":
            s += "<%s %s>" % (e[1], bug_compat_render_term(e[2]))
        elif e[0] == "text":
            s += e[1]
        else:
            assert(False)
    return s


def only_honr(tree):
    tags = set()
    for e in tree:
        if "tag" in e:
            tags.add(e.get("tag"))
    return tags == set(["HONR"])

def parse_field(field, metapost_entry):
    (key, rawvalue, fieldname, subordinates, lang) = field
    extra = []
    rows = rawvalue.split("\u2029")
    #(_value, _embedded_fields, converted_tree) = parse_embedded(rawvalue)
    converted_trees = [parse_embedded(row)[2] for row in rows]
    only_text = all([len(e) == 1 and e[0][0] == "text" for e in converted_trees])
    if only_text:
        only_text_value = "\u2029".join([e[0][1] for e in converted_trees])
    if fieldname in ["TE", "SYTE", "AVTE", "PH", "SYPH", "INTE"]:
        if only_text:
            if "\u2029" in only_text_value:
                log("Nytt stycke i term:", only_text_value)
            tree = named_tag_tree(only_text_value, "{", "}", log=log)
            if tree == None:
                field = {"term": string_substitutions(only_text_value)}
            elif len(tree) == 1 and tree[0].keys() == set(["text"]):
                field = {"term": tree[0]["text"]}
            else:
                field = {"annotated_term": tree}
        else:
            # XXX Bug compatibility
            log("Inte bara text i term:", converted_trees)
            termstring = "\u2029".join([bug_compat_render_term(e) for e in converted_trees])
            field = {"term":string_substitutions(termstring)}

        if fieldname in ["TE", "SYTE", "PH", "SYPH"]:
            if splitPreferredAdmitted(metapost_entry, lang):
                field["split"] = True
        for k,v in subordinates:
            if k == "GE":
                field["geo"] = v
            elif k == "HONR":
                field["homonym"] = int(v)
            elif k == "GNGR":
                field["gender"] = " eller ".join([e.strip() for e in v.split(",")])
            elif k == "GR":
                field["grammar"] = v
            elif k == "UT":
                field["pronunciation"] = v
            elif k == "BNGR":
                definite_or_neuter, _, plural = v.partition(" ")
                if not definite_or_neuter:
                    definite_or_neuter = None
                if not plural:
                    plural = None
                parsed_inflection = parse_inflection(v)
                if parsed_inflection:
                    field.setdefault("inflection", []).extend(parsed_inflection)
            elif k == "OKGR":
                if metapost_entry.get("Tolka_OKGR-märkning", "baraOmInteOrdklassSjälvklar") == "baraOmInteOrdklassSjälvklar":
                    field["pos_not_obvious"] = True
                    field["pos"] = v
            elif k == "SA":
                field["narrowing"] = string_substitutions(v)
            elif k == "RF":
                field["source"] = string_substitutions(v) # XXX also breaks URLs
            elif k == "ETYM":
                field["etymology"] = string_substitutions(v)
            elif k == "FRKT":
                if v.lower() == "of":
                    field["full form"] = True
                elif v.lower() == "f":
                    field["abbreviation"] = True
                else:
                    log("Ogiltig förkortningsstatus", v)
            else:
                log("Oimplementerat kopplat fält", k, "under toppnivåfält", fieldname)
        if fieldname == "PH":
            field["status"] = "TE"
            field["phrase"] = True
        elif fieldname == "SYPH":
            field["status"] = "SYTE"
            field["phrase"] = True
        else:
            field["status"] = fieldname
        field["lang"] = lang
        if "term" in field:
            extra.extend([("searchterms", e) for e in split_searchterm(field["term"])])
        if "annotated_term" in field:
            extra.extend([("searchterms", e) for e in split_searchterm(textconvert_annotated_term(field["annotated_term"]))])
        return [("terms", field)] + extra
    elif fieldname == "UPTE":
        assert(only_text)
        split_value = only_text_value.split(",")
        fields = [("onlysearch", {"term":string_substitutions(s.strip()), "lang": lang}) for s in split_value]

        for k,v in subordinates:
            if k == "OKGR":
                for field in fields:
                    if metapost_entry.get("Tolka_OKGR-märkning", "baraOmInteOrdklassSjälvklar") == "baraOmInteOrdklassSjälvklar":
                        field[1]["pos_not_obvious"] = True
                    field[1]["pos"] = v
            elif k == "ETYM":
                pass
            else:
                log("Oimplementerat kopplat fält", k, "under toppnivåfält", fieldname)
        for _, fvalue in fields:
            extra.extend([("searchterms", e) for e in split_searchterm(fvalue["term"])])
        return fields + extra
    elif fieldname == "ILLU" or fieldname == "IL":
        assert(only_text)
        filename = only_text_value
        illustration_entries = metapost_entry.setdefault("illustrations", {})
        illustration_field = illustration_entries.setdefault(filename, {"filename":filename})
        for k,v in subordinates:
            if k == "ILLT":
                illustration_field["text"] = string_substitutions(v)
            elif k == "ILTY":
                if v == "begreppsdiagram":
                    illustration_field["type"] = "concept diagram"
                else:
                    log("Oimplementerat illustrationstyp", v, "i", k)
            else:
                log("Oimplementerat kopplat fält", k, "under toppnivåfält", fieldname)
        return [(key, illustration_field.copy())] + extra
    elif fieldname == "INID":
        assert(only_text)
        try:
            return [(key, int(only_text_value))]
        except ValueError:
            #log("Invalid internal ID:", only_text_value)
            return []
    elif fieldname in ["INAN", "RIAN"]:
        assert(only_text)
        return [("internal_comment", string_substitutions(only_text_value))]
    elif fieldname in ["DF", "FK", "AN", "EX", "SA", "EKVI", "KLAR"]:
        textrows = []
        for converted_tree in converted_trees:
            if not only_text:
                if len(converted_tree) == 1 and converted_tree[0][0] == "text":
                    textrows.append({"text": string_substitutions(converted_tree[0][1])})
                else:
                    if only_honr(format_tree(converted_tree)):
                        textrows.append({"text": embeddedconvert_annotated_term(format_tree(converted_tree))})
                    else:
                        textrows.append({"annotated_text": handle_rcon(format_tree(converted_tree))})
            else:
                tree = named_tag_tree(string_substitutions(converted_tree[0][1]), "{", "}", log=log)
                if tree == None:
                    textrows.append({"text": string_substitutions(converted_tree[0][1])})
                elif len(tree) == 1 and tree[0].keys() == set(["text"]):
                    textrows.append({"text": tree[0]["text"]})
                else:
                    textrows.append({"annotated_text": tree})
        field = {"paragraphs": textrows}
        for k,v in subordinates:
            if k == "RF":
                field["source"] = string_substitutions(v) # XXX also breaks URLs
            elif k == "ETYM":
                pass # ignore ETYM field when under text field
            else:
                log("Oimplementerat kopplat fält", k, "under toppnivåfält", fieldname)
        field["lang"] = lang
        text_types = {"DF":"definition", "FK":"explanation", "EX": "example",
                          "AN": "comment", "SA": "domain", "EKVI": "equivalence", "KLAR": "plain"}
        field["type"] = text_types[fieldname]
        #print(field)
        for textrow in textrows:
            if "annotated_text" in textrow:
                extra.extend([("fulltextsearch", e) for e in split_searchterm(textconvert_annotated_text(textrow["annotated_text"]))])
            else:
                extra.extend([("fulltextsearch", e) for e in split_searchterm(textrow["text"])])
        return [("texts", field)] + extra
    elif fieldname == "KT":
        assert(only_text)
        textrows = []
        for converted_tree in converted_trees:
            tree = named_tag_tree(string_substitutions(converted_tree[0][1]), "{", "}", log=log)
            if tree == None:
                textrows.append({"text": string_substitutions(converted_tree[0][1])})
            elif len(tree) == 1 and tree[0].keys() == set(["text"]):
                textrows.append({"text": tree[0]["text"]})
            else:
                textrows.append({"annotated_text": tree})

        field = {
            "paragraphs": textrows,
            "lang": lang,
            "type": "context",
        }
        return [("texts", field)]
    if fieldname == "RETE":
        assert(len(converted_trees) == 1)
        value = split_embedded_converted(converted_trees[0], ",")
        result = [("seealso", pack_RETE(*e, lang)) for e in value]
    elif fieldname == "SU":
        assert(len(converted_trees) == 1)
        value = split_embedded_converted(converted_trees[0], ",")
        result = [("seeunder", pack_RETE(*e, lang)) for e in value]

    elif fieldname == "RIFR":
        return []
    elif fieldname == "KL":
        return []
    elif fieldname == "BT":
        assert(only_text)
        if "\u2029" in only_text_value:
            log("Nytt stycke i beteckning:", only_text_value)
        tree = named_tag_tree(only_text_value, "{", "}", log=log)
        if tree == None:
            term = {"term": string_substitutions(only_text_value)}
        elif len(tree) == 1 and tree[0].keys() == set(["text"]):
            term = {"term": tree[0]["text"]}
        else:
            term = {"annotated_term": tree}

        term["status"] = "BT"
        term["lang"] = lang
        result = [("terms", term)]
        if "term" in term:
            result.extend([("searchterms", e) for e in split_searchterm(term["term"])])
        if "annotated_term" in term:
            searchterms = split_searchterm(textconvert_annotated_term(term["annotated_term"]))
            result.extend([("searchterms", e) for e in searchterms])
    elif fieldname == "TI":
        result = []
    else:
        if only_text:
            result = [(key, string_substitutions(only_text_value))]
        else:
            # XXX
            result = [(key, string_substitutions("\u2029".join([bug_compat_render_term(e) for e in converted_trees])))]
    for k,v in subordinates:
        #assert(only_text) # XXX
        if k == "ETYM":
            continue # ignore ETYM field
        log("Oimplementerat kopplat fält", k, "under toppnivåfält", fieldname)
    return result

def readfile(f):
    global_entry = None
    metapost_entry = None
    entries = []
    for entry_rows in entry_generator(f):
        if global_entry == None:
            #print("global entry", entry)
            global_entry = parse_header_entry(entry_rows)
            if "global" not in global_entry and "metapost" in global_entry:
                metapost_raw = global_entry
                assert(metapost_raw["metapost"] == "")
                metapost_entry = transform_metapost(metapost_raw)
        elif metapost_entry == None:
            #print("metapost entry", entry)
            metapost_raw = parse_header_entry(entry_rows)
            assert(metapost_raw)
            #assert(metapost_raw["metapost"] == "")
            metapost_entry = transform_metapost(metapost_raw)
        elif entry_rows[0] == "metapost":
            break
        else:
            #print("normal entry", entry)
            entries.append(parse_entry(entry_rows, metapost_entry))
        #print()
    assert(global_entry)
    return (global_entry, metapost_entry, entries)

def handle_utgivare(utgivare, components, value):
    try:
        index = int(components[1])-1
    except ValueError:
        log("Ogiltigt listnummer för utgivare:", components)
        return
    type = components[2]
    while len(utgivare) < index+1:
        utgivare.append({})
    utgivare[index]["type"] = type
    utgivare[index][components[3]] = value

def handle_klassifikationssystem(klassifikationssystem, components, value):
    index = int(components[1])-1
    while len(klassifikationssystem) < index+1:
        klassifikationssystem.append({})
    klassifikationssystem[index][components[2]] = string_substitutions(value)

def transform_metapost(rows):
    metapost = {}
    for k, v in rows.items():
        if not v:
            continue
        #print(k, v)
        if k == "metapost":
            continue
        if "." in k:
            components = k.split(".")
            if components[0] == "Utgivare" and len(components) == 4:
                utgivare = metapost.setdefault("Utgivare", [])
                handle_utgivare(utgivare, components, v)
            elif components[0] == "Klassifikationssystem" and len(components) == 3:
                klassifikationssystem = metapost.setdefault("Klassifikationssystem", [])
                handle_klassifikationssystem(klassifikationssystem, components, v)
            else:
                k = "_".join(components)
                if k in ["Titel_kortform", "Titel_överordnad"]:
                    v = string_substitutions(v)
                metapost[k] = v
            continue
        if k in ["Ställe", "Titel"]:
            v = string_substitutions(v)
        assert(k not in metapost)
        metapost[k] = v
    #print(metapost)
    return metapost

def read_one(db, filename, slug_to_termpostid, metadata, gitversion):
    basename = os.path.basename(filename)
    #db.termpost_.aggregate([{"$group":{"_id": null, "max":{"$max":"$id"}}}])

    clearlog()
    
    f = open(filename, encoding='utf-8')
    try:
        header, metapost, entries = readfile(f)
    except UnicodeDecodeError:
        log("Avkodningsfel i fil:", filename)
        return getlog()
    except ValueError as err:
        log("Tolkningsfel i fil:", filename, err)
        traceback.print_tb(err.__traceback__)
        return getlog()
    except Exception as err:
        print("Tolkningsfel i fil:", filename, err)
        traceback.print_tb(err.__traceback__)
        sys.exit(1)

    if "Källid" not in metapost:
        log("Källid finns inte med i metadatahuvudet")
        return getlog()

    kalla_id = int(metapost["Källid"])
    metadata["kallid"] = kalla_id
    del metapost["Källid"]

    if "Status" not in metapost:
        log("Status finns inte med i metadatahuvudet")
        return getlog()
    status_text = metapost["Status"]
    del metapost["Status"]
    if status_text == "publicerad":
        kalla_status = 2
    elif status_text in ["avpublicerad", "inaktuell"]:
        kalla_status = 1
    elif status_text in ["inteFärdig", "bearbetas"]:
        kalla_status = 0
    else:
        log("Ogiltig status i metadatahuvudet:", status_text)
        return getlog()

    assert("id" not in metapost)
    metapost["id"] = kalla_id
    if "Tolka_OKGR-märkning" in metapost:
        del metapost["Tolka_OKGR-märkning"]
    for k in list(metapost.keys()):
        if k.startswith("Tolka_skillnadTermSynonym_"):
            del metapost[k]
    metapost["filename"] = basename

    entries_lookup = {}
    for entry in entries:
        if "terms" not in entry:
            log("Inga termer i termposten:", entry)
            continue
            #entries_lookup = {}
            #break
        terms = entry["terms"]
        for term in terms:
            if term["status"] == "AVTE":
                continue
            lang = term["lang"]
            term_key = (term.get("term", ""), term.get("homonym", 0))
            entries_lookup.setdefault(lang, {})
            entries_lookup[lang].setdefault(term_key, []).append(entry)

    if "Klassifikationssystem" in metapost:
        del metapost["Klassifikationssystem"]
    if "illustrations" in metapost:
        del metapost["illustrations"]
    metapost["errors"] = getlog()
    metapost["status"] = kalla_status
    metapost["gitversion"] = gitversion
    db.kalla.insert_one(metapost)

    termposts = []

    for entry in entries:
        if "terms" in entry:
            slugs = get_slugs(entry["terms"])
            termpostid = None
            for slug in slugs:
                termpostid = slug_to_termpostid.get((slug, kalla_id))
                if termpostid:
                    break
            if termpostid:
                entry["id"] = termpostid
            entry["slugs"] = slugs
            assert("kalla" not in entry)
            for e in metapost["Utgivare"]:
                l = []
                if e.get("organisation", ""):
                    l.append(e["organisation"])
                if e.get("avdelning", ""):
                    l.append(e["avdelning"])
                if e.get("författare", ""):
                    l.append(e["författare"])
                # XXX reuses past value of publisher if there is no publisher
                publisher = ", ".join(l)
            if "seealso" in entry:
                seealso = [seealso_convert(e, entries_lookup) for e in entry["seealso"]]
                seealso = list(filter(lambda x: x is not None, seealso))
                entry["seealso"] = unique(seealso, key=lambda x: json.dumps(x, sort_keys=True))
                if not entry["seealso"]:
                    del entry["seealso"]
            if "seeunder" in entry:
                seealso = [seealso_convert(e, entries_lookup) for e in entry["seeunder"]]
                seealso = list(filter(lambda x: x is not None, seealso))
                entry["seeunder"] = unique(seealso, key=lambda x: json.dumps(x, sort_keys=True))
                if not entry["seeunder"]:
                    del entry["seeunder"]
            if "onlysearch" in entry:
                entry["onlysearch"] = unique(entry["onlysearch"], key=lambda x: json.dumps(x, sort_keys=True))
            entry["terms"] = unique(entry["terms"], key=lambda x: json.dumps(x, sort_keys=True))

#            if "Titel_kortform" not in metapost:
#                titel = metapost.get("Titel", None)
#            else:
#                titel = metapost.get("Titel_kortform", None)
            entry["kalla"] = {
                "id": kalla_id,
                "year": metapost.get("Utgivningsår", None),
#                "title": titel,
                "title": metapost.get("Titel_kortform", None),
                "publisher": publisher,
                "place": metapost.get("Ställe", None),
                "status": kalla_status,
            }
            entry["gitversion"] = gitversion
            termposts.append(entry)
    db.termpost.insert_many(termposts)
    return getlog()

def getmatch(term_entry, term):
    matches = [e for e in term_entry["terms"] if e["term"] == term]
    #print("getmatch", term_entry)
    #print(term)
    #print(matches)
    return matches[0]

def bestmatch_term(term_entries, term):
    #print("bestmatch_term", term_entries)
    matches = [getmatch(e, term) for e in term_entries]
    if len(term_entries) == 0:
        return None
    elif len(term_entries) == 1:
        return term_entries[0]
    elif len(term_entries) == 2:
        if matches[0]["status"] == "TE" and matches[1]["status"] == "SYTE":
            return term_entries[0]
        elif matches[0]["status"] == "SYTE" and matches[1]["status"] == "TE":
            return term_entries[1]
        else:
            return term_entries[0]
    #print("    ", len(term_entries), matches)
    assert(len(term_entries) == 1)
    term_entry = term_entries[0]
    return term_entry

def seealso_convert(seealso, entries_lookup):
    term = seealso["term"]
    lang = seealso["lang"]
    if lang == "sv":
        return seealso
    homonym = seealso.get("homonym", 0)
    #print("seealso_convert", term, lang, homonym)
    found_terms = entries_lookup.get(lang, {}).get((term, homonym), [])
    if not found_terms:
        log("Hittade inte exakt refererad termpost:", term, lang, homonym)
    term_entry = bestmatch_term(found_terms, term)
    if term_entry is None:
        log("Även luddigare sökning efter refererad termpost misslyckades:", term, lang, homonym)
        return None
    terms = term_entry["terms"]
    #print("    ", terms)
    #print("    ", sort_terms(terms))
    seealso = {"term":terms[0]["term"], "lang": terms[0]["lang"]}
    if "homonym" in terms[0]:
        seealso["homonym"] = terms[0]["homonym"]
    return seealso

import sys

def default_log(*s):
    print(*s)

def find_all(haystack, needle):
    result = []
    pos = 0
    while True:
        pos = haystack.find(needle, pos)
        if pos == -1:
            break
        result.append(pos)
        pos += 1
    return result

import html
import re

def decode_entities(text):
    text = text.replace("--", "\u2013")
    text = text.replace("-+-", "\u2212")
    text = text.replace("_", "\u00a0")
    text = text.replace("\u001e", "\u2013")
    text = re.sub(r"\\u[’']([0-9A-F]{4})[’']", "&#x\\g<1>;", text)
    text = html.unescape(text)
    return text


def cut_tree(s, tags, log=default_log):
    begintags = []
    subtree = []
    for startpos, endpos, subtrees in tags:
        assert(not subtrees)
        tagname = s[startpos+1:endpos]
        if len(tagname) == 0:
            continue
        elif tagname[0] == "/":
            if not begintags:
                continue
            while begintags:
                lasttag = begintags.pop()
                if lasttag[0] == tagname[1:]:
                    subtree.append(lasttag[1])
                    subtree.append((startpos, endpos, subtrees))
                    break
        else:
            begintags.append((tagname, (startpos, endpos, subtrees)))
    return sorted(subtree)


def named_tag_subtree(s, tags, content_start, log=default_log):
    tree = []
    #log("named_tag_subtree", s, tags, content_start, s[content_start:])
    while tags:
        startpos, endpos, subtrees = tags.pop(0)
        assert(not subtrees)
        tagname = s[startpos+1:endpos]
        #print("tag:", tagname)
        if len(tagname) == 0:
            #log("subtree returns, tagname empty")
            return (tree + [{"text":"{}"}], None, None, None, content_start)
        elif tagname[0] == "/":
            #log("subtree returns, end tag")
            return (tree, tagname[1:], startpos, endpos, content_start)
        else:
            subtree, endtag_name, endtag_startpos, endtag_endpos, inner_tag_end = named_tag_subtree(s, tags, endpos+1, log=default_log)
            if subtree == None:
                #log("error: subtree returns, None inside: " + s)
                return (tree, None, None, None, None)
            #print("tagname", tagname, "endtag", endtag_name)
            if tagname != endtag_name:
                #log("error: subtree returns, tagname != endtag_name", tagname, endtag_name)
                return (tree, None, None, None, None)
            assert(tagname == endtag_name)
            if s[content_start:startpos]:
                tree.append({"text":decode_entities(s[content_start:startpos])})
            if s[inner_tag_end:endtag_startpos]:
                subtree.append({"text":decode_entities(s[inner_tag_end:endtag_startpos])})
            tree.append({"tag": tagname, "content": subtree})
            content_start = endtag_endpos + 1
    #log("subtree returns, normal")
    return (tree, None, None, None, content_start)

def named_tag_tree(s, tag_start, tag_end, log=default_log):
    tags = tag_tree(s, tag_start, tag_end, log=log)
    if any([subtrees for startpos, endpos, subtrees in tags]):
        log("klammerparenteser inuti varandra:", s)
        return None
    #print(s, tags)
    tags = cut_tree(s, tags, log=log)
    subtree, endtag_name, endtag_startpos, endtag_endpos, inner_tag_end = named_tag_subtree(s, tags, 0, log=log)
    if subtree == None:
        #log("error: subtree None: " + s)
        return None
    if endtag_name is not None:
        subtree.append({"text":"endtag:" + repr(endtag_name)})
    if tags:
        subtree.append({"text":"tags:"+repr(tags)})
    #assert(endtag_name == None)
    #assert(tags == [])
    tree = subtree
    if s[inner_tag_end:]:
        tree = tree + [{"text":decode_entities(s[inner_tag_end:])}]
    return tree

def build_subtree(positions, log=default_log):
    if not positions:
        return []
    startpos, start = positions[0]
    if not start:
#        log("end symbol without start symbol")
        return (None, [])
    assert(start)
    positions = positions[1:]
    subtrees = []
    if not positions:
#        log("illegal tag, no end symbol")
        return (None, [])
    while positions[0][1]:
        (subtree, positions) = build_subtree(positions, log=log)
        if not positions:
#            log("illegal tag, no end symbol")
            return (None, [])
        if subtree != None:
            subtrees.append(subtree)
    endpos, _ = positions[0]
    positions = positions[1:]
    return ((startpos, endpos, subtrees), positions)

def build_tree(positions, log=default_log):
    tree = []
    while positions:
        (subtree, positions) = build_subtree(positions, log=log)
        if subtree != None:
            tree.append(subtree)
    return tree

def tag_tree(s, tag_start, tag_end, log=default_log):
    start_tag_positions = [(pos, True) for pos in find_all(s, tag_start)]
    end_tag_positions = [(pos, False) for pos in find_all(s, tag_end)]
    positions = sorted(start_tag_positions + end_tag_positions)
    return build_tree(positions, log=log)


if __name__ == "__main__":
    import json
    test_strings = [
        "In this {i}sentence{/i}, all {i}nouns{/i} are italicized.",
        "In this sentence, this {sup}part of the {i}sentence{/i} is lower{/sup}."
    ]
    for s in test_strings:
        tree = named_tag_tree(s, "{", "}")
        print(json.dumps(tree, indent=4))
        print()

def rename_dict(d, translations):
    return {translations.get(k, k):v for k, v in d.items()}

term_status_prio = {
    "TE": 0,
    "SYTE": 1,
    "AVTE": 2,
}

term_lang_prio = {
    "sv": 0,
    "en": 1,
    "de": 2,
    "fr": 3,
    "es": 4,
    "ca": 5,
    "rom": 6,
    "la": 7,
    "da": 8,
    "fo": 9,
    "is": 10,
    "nb": 11,
    "nn": 12,
    "no": 13,
    "hr": 14,
    "pl": 15,
    "ru": 16,
    "gr": 17,
    "fi": 18,
    "fit": 19,
    "se": 20,
    "et": 21,
    "kl": 22,
    "tr": 23,
    "ku": 24,
    "ar": 25,
    "so": 26,
    "ja": 27,
    "nl": 28,
    "it": 29,
    "re": 30,
    "em": 31,
    "pt": 32,
    "il": 33,
    "sy": 34,
    "sq": 35,
    "rm": 36,
    "rk": 37,
    "ra": 38,
}

def get_lang_prio(lang):
    if lang not in term_lang_prio:
        print(lang, "not in term_lang_prio", file=sys.stderr)
        sys.exit(1)
    return term_lang_prio.get(lang, 100)

def sort_terms_key(term):
    return (
        term_status_prio.get(term["status"], 100),
        get_lang_prio(term["lang"]),
        "term" in term,
        term.get("term", ""),
    )

def sort_lang_codes(codes):
    return sorted(codes, key=lambda code: term_lang_prio.get(code, 100))

def sort_terms(terms):
    return sorted(terms, key=sort_terms_key)

def split_searchterm(term):
    return [e.strip() for e in term.split(" ") if e]

def multidict_add(d, entries):
    for k, v in entries:
        d.setdefault(k, []).append(v)

def unique(l, key=None):
    result = []
    keys = set()
    for e in l:
        k = key(e)
        if k not in keys:
            result.append(e)
            keys.add(k)
    return result

def textconvert_annotated_term(annotated_term):
    s = ""
    for e in annotated_term:
        if "text" in e:
            s += e["text"]
        elif "tag" in e:
            s += textconvert_annotated_term(e["content"])
        else:
            assert(False)
    return s

def embeddedconvert_annotated_term(annotated_term):
    s = ""
    for e in annotated_term:
        if "text" in e:
            s += e["text"]
        elif "tag" in e:
            s += "<" + e["tag"] + " " + embeddedconvert_annotated_term(e["content"]) + ">"
        else:
            assert(False)
    return s

def textconvert_annotated_text(annotated_text):
    s = ""
    for e in annotated_text:
        if "text" in e:
            s += e["text"]
        elif "tag" in e:
            s += textconvert_annotated_text(e["content"])
        elif "term" in e:
            s += e["term"]["term"]
        else:
            print(annotated_text)
            print(e)
            assert(False)
    return s

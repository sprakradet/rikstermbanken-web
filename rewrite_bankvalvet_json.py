import json
import collections
from pathlib import Path

def move_keys(first, last, keys):
    first = [k for k in first if k in keys]
    last = [k for k in last if k in keys]
    keys = [k for k in keys if k not in first+last]
    return first + keys + last

def dict_order(path, keys):
    if path == "/termposts/terms":
        return move_keys(["lang", "status", "term", "annotated_term"], [], keys)
    elif path == "/termposts/texts":
        return move_keys(["lang", "type", "paragraphs"], [], keys)
    elif path == "/termposts":
        return move_keys(["id", "kalla", "terms", "texts", "seealso", "seeunder"], ["searchterms", "INID"], keys)
    elif path == "/termposts/kalla":
        return move_keys(['id', 'status', 'publisher', 'year', 'title', 'place'], [], keys)
    elif path == "/termposts/seealso" or path == "/termposts/seeunder":
        return move_keys(['lang', 'term', 'homonym'], [], keys)
    elif path.startswith("/termposts/terms/annotated_term"):
        return move_keys(["tag", "content", "text"], [], keys)
    elif path == "/termposts/texts/paragraphs":
        return keys
    elif path.startswith("/termposts/texts/paragraphs/annotated_text"):
        return move_keys(["tag", "content", "text"], [], keys)
    elif path == "/termposts/onlysearch":
        return move_keys(["lang", "term"], [], keys)
    elif path == "/termposts/ILLU":
        return move_keys(['filename', 'text'], [], keys)
    if path == "/termposts/classifications":
        return move_keys(['value', 'system'], [], keys)
    elif path == "/termposts/classifications/system":
        return move_keys(['name', 'short_name', 'url', 'description'], [], keys)
    elif path == "/termposts/terms/inflection":
        return move_keys(['definite_or_neuter', 'plural', 'collective'], [], keys)
    elif path == "/kalla/Utgivare":
        return move_keys(['type', 'organisation'], [], keys)
    elif path == "/kalla/Klassifikationssystem":
        return move_keys(['namn', 'kortnamn', 'url', 'beskrivning'], [], keys)
    elif path == "/kalla":
        return move_keys([], [], keys)
    elif path == "":
        return move_keys(['kalla', 'termposts'], [], keys)
    else:
        print(path, keys)
        return keys

def reorder_dicts(node, path=""):
    if isinstance(node, (list)):
        return [reorder_dicts(e, path) for e in node]
    elif isinstance(node, (dict)):
        result = {}
        for k in dict_order(path, node.keys()):
            result[k] = reorder_dicts(node[k], path=path+"/"+k)
        return result
    return node

rootdir = Path(".")
all_fileobjects = list(rootdir.glob('**/*.json'))
for fileobject in all_fileobjects:
    if fileobject.name in ["termlistor.json", "id_slugs.json"]:
        continue
    indata = json.load(open(fileobject))
    outdata = reorder_dicts(indata)
    # rewrite outdata here
    if json.loads(json.dumps(outdata)) == json.loads(json.dumps(indata)):
        continue
    json.dump(outdata, open(fileobject, "wt"), ensure_ascii=False, indent=4)

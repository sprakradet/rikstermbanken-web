import sys
from pathlib import Path
import json
import collections
import unicodedata
import subprocess

import pymongo
from pymongo import MongoClient
from pymongo.collation import Collation

import import_one

import updatecfg

client = MongoClient(connect=False,
                     username=updatecfg.MONGODB_USERNAME,
                     password=updatecfg.MONGODB_PASSWORD,
                     authSource=updatecfg.MONGODB_DB)

rootdir = Path(sys.argv[1])

git_rev_parse = subprocess.run(["git", "-C", rootdir, "rev-parse", "HEAD"], stdout=subprocess.PIPE)
git_rev_parse.check_returncode()
gitversion = git_rev_parse.stdout.decode("ascii").strip()
#print("***", gitversion, "***")

db = client.rikstermbanken_staging

prev_import_status = db.status.find_one({"key":"import"})
if prev_import_status and prev_import_status.get("gitversion") == gitversion:
    print("Samma gitversion som vid förra importen:", prev_import_status.get("gitversion"))
    sys.exit(0)

db.termpost.delete_many({})
db.kalla.delete_many({})
db.status.delete_one({"key":"import"})

db.termpost.drop_indexes()
db.termpost.create_index([("id", pymongo.ASCENDING)])
db.termpost.create_index([("terms.term", pymongo.ASCENDING),
                          ("kalla.id", pymongo.ASCENDING)])
collation = Collation("sv@collation=search", strength=2)
db.termpost.create_index([("searchterms", pymongo.ASCENDING)],
                         collation=collation)
db.termpost.create_index([("kalla.id", pymongo.ASCENDING),
                          ("slugs", pymongo.ASCENDING)], unique=True)


termpost_slugs = json.load(open(rootdir / "id_slugs.json"))
slug_to_termpostid = {}
for slugmapping in termpost_slugs:
    for slug in slugmapping["slugs"]:
        slug_to_termpostid[(slug, slugmapping["kalla"])] = slugmapping["id"]

handled_kallid = set()

nsources = 0

for fullpath in rootdir.glob('**/*.txt'):
    metadata = {}
    log = import_one.read_one(db, fullpath, slug_to_termpostid, metadata, gitversion)
    handled_kallid.add(metadata["kallid"])
    nsources += 1
    if log:
        print()
        print()
        print("===========================================")
        print(metadata["kallid"], fullpath)
        print("===========================================")
        print()
        for row in log:
            print(*row)

termposts = []
sources = []
nummer_fileobjects = list(rootdir.glob('oklara/*.json'))
for fileobject in nummer_fileobjects:
    filename_json = fileobject.name
    assert filename_json[-5:] == ".json"
    source_id = int(filename_json[:-5])
    if source_id in handled_kallid:
        print("error:", source_id, "already handled and exists as 'oklara' JSON")
        sys.exit(1)
    source = json.load(open(fileobject))
    source["kalla"]["filename"] = fileobject.name
    for entry in source["termposts"]:
        entry["gitversion"] = gitversion
    termposts.extend(source["termposts"])
    source["kalla"]["gitversion"] = gitversion
    sources.append(source["kalla"])
    nsources += 1

print("writing to database")
if sources:
    db.kalla.insert_many(sources)
if termposts:
    db.termpost.insert_many(termposts)

db.status.insert_one({"key":"import", "gitversion": gitversion, "nsources": nsources})

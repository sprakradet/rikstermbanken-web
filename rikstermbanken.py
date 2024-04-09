from flask import Flask, request, session, url_for, redirect, \
     render_template, abort, g, flash, make_response, current_app, jsonify, Blueprint, Response
from flask_babel import Babel
from import_util import term_lang_prio, sort_lang_codes, textconvert_annotated_term
from typing import NamedTuple, List, Any
from urllib.parse import quote_plus

import flask
import datetime
import sys
import os
import time
import secrets
from flask import send_from_directory
import pymongo
import pymongo.errors
from pymongo import MongoClient
from bson.regex import Regex
import itertools
import jinja2
import markupsafe
import mongodbcfg
import admincfg

try:
    from rb_version import RIKSTERMBANKEN_WEB_VERSION
except (ImportError, ModuleNotFoundError):
    RIKSTERMBANKEN_WEB_VERSION = ""

os.environ['TZ'] = 'Europe/Stockholm'
time.tzset()

bp = Blueprint('rtb', __name__, url_prefix='/')
bp_debug = Blueprint('debug', __name__, url_prefix='/debug/')
bp_login = Blueprint('login', __name__, url_prefix='/')
client = MongoClient(connect=False,
                     username=mongodbcfg.MONGODB_USERNAME,
                     password=mongodbcfg.MONGODB_PASSWORD,
                     authSource=mongodbcfg.MONGODB_DB)

def log_access(page, *args):
    client.rikstermbanken_log.get_collection("accesslog", write_concern=pymongo.write_concern.WriteConcern(w=0)).insert_one({"time": time.time(), "page": page, "args": args})

@bp.errorhandler(pymongo.errors.ServerSelectionTimeoutError)
def handle_server_timeout(error):
    response = make_response(render_template('rtb_error.html'))
    response.status_code = 500
    return response

@bp.errorhandler(500)
def page_not_found(e):
    return render_template('500.html'), 500

@bp.route('/')
def start_page():
    log_access("/")
    return render_template('rtb_main.html')


@bp.route('/mainMenu.html')
@bp.route('/startSimpleSearch.html')
def redirect_main():
    log_access("/mainMenu.html")
    return render_template('rtb_main.html')

@bp.route('/ts/startAdvancedSearch.html')
def advancedsearch():
    log_access("/ts/startAdvancedSearch.html")
    return render_template('rtb_advancedsearch.html')

@bp.route('/kallor.html')
def kallor():
    log_access("/kallor.html")
    sources = db.termpost.aggregate([{"$match": {"kalla.status": 2}}, {"$group":{"_id": "$kalla", "count":{"$sum":1}}}])
    sources = sorted(sources, key=lambda source: (source["_id"]["publisher"], source["_id"]["title"] or "", source["_id"]["id"]))
    return render_template('rtb_kallor.html', sources=sources)

@bp.route('/nyheter.html')
def nyheter():
    log_access("/nyheter.html")
    return render_template('rtb_nyheter.html')

@bp.route('/fragorochsvar.html')
def fragorochsvar():
    log_access("/fragorochsvar.html")
    return render_template('rtb_fragorochsvar.html')

@bp.route('/hjalp.html')
def hjalp():
    log_access("/hjalp.html")
    return render_template('rtb_hjalp.html')

@bp.route('/om.html')
def om():
    log_access("/om.html")
    return render_template('rtb_om.html')

@bp.route('/kontakt.html')
def kontakt():
    log_access("/kontakt.html")
    return render_template('rtb_kontakt.html')

@bp.route('/visaKalla.html')
def visaKalla():
    try:
        id = int(request.args.get("id"))
    except (ValueError, TypeError):
        return render_template('404.html'), 404
    log_access("/visaKalla.html")
    kalla = db.kalla.find_one({
        "id": id,
        })
    if kalla is None:
        return render_template('404.html'), 404
    ntermposts = db.termpost.count_documents({"kalla.id": id})
    return render_template('rtb_kalla.html', kalla=kalla, ntermposts=ntermposts)

@bp.route('/startSkickaSynpunkter.html')
def skickaSynpunkter():
    log_access("/startSkickaSynpunkter.html")
    return render_template('rtb_synpunkter.html')

def group_match_lang(l):
    result = []
    for k, g in itertools.groupby(l, key=lambda x: x["match"]["lang"]):
        result.append({"lang":k, "matches":list(g)})
    return result

term_prio = {
    "TE":0,
    "SYTE":1,
    "AVTE":2,
}

def match_sortkey(match):
    matchquality = matchquality_prio.get(match["type"], 100)
    return (matchquality, term_lang_prio.get(match["match"]["lang"], 100), term_prio.get(match["match"]["status"], 100))

def restrict_matches(matches):
    if not matches:
        return matches
    grouped = group_match_lang(matches)
    if grouped[0]["lang"] == "sv":
        if len(grouped) > 1:
            return grouped[0]["matches"] + [grouped[1]["matches"][0]]
        else:
            return grouped[0]["matches"]
    else:
        return [grouped[0]["matches"][0]]

def get_term_text(term):
    if "term" in term:
        return term["term"]
    elif "annotated_term" in term:
        return textconvert_annotated_term(term["annotated_term"])
    else:
        return ""

def match(terms, searchStringExpressions):
    matches = []
    for term in terms:
        term_text = get_term_text(term)
        splitterm = [t.casefold() for t in term_text.split(" ")]
        if all([e.isString() for e in searchStringExpressions]) and term_text.casefold() == " ".join([e.casefold() for e in searchStringExpressions]):
            matches.append({"type":"exact", "match":term, "text": term_text})
        else:
            matched = False
            for searchStringExpression in searchStringExpressions:
                if searchStringExpression.matchesAny(term_text.split(" ")):
                    matched = True
            if matched:
                matches.append({"type":"partial", "match":term, "text": term_text})
    matches = sorted(matches, key=match_sortkey)
    matches = restrict_matches(matches)
    if not any([match["match"]["status"] == "TE" for match in matches]):
        matches = [{"type": "canonical", "match":term, "text": get_term_text(term)} for term in terms if term["status"] == "TE" and term["lang"] == "sv"] + matches
    if not any([match["match"]["lang"] == "sv" for match in matches]):
        matches = [{"type": "canonical", "match":term, "text": get_term_text(term)} for term in terms if term["status"] == "TE" and term["lang"] == "sv"] + matches
    if not any([match["match"]["lang"] == "sv" and match["match"]["status"] == "TE" for match in matches]):
        matches = [{"type": "canonical", "match":term, "text": get_term_text(term)} for term in terms if term["status"] == "TE" and term["lang"] == "sv"] + matches
    return matches


class TextPrioKey(NamedTuple):
    type: int
    lang: int

class KallaSortKey(NamedTuple):
    year: int
    title: str
    publisher: str

class TermSortKey(NamedTuple):
    lang: int
    quality: int
    matchedterms: List[str]
    kalla: KallaSortKey
    homonym: List[int]
    tiebreak_terms: List[str]

matchquality_prio = {
    "exact":0,
    "partial":1,
}

def sortkey(term, lang, searchStringExpressions):
#    print(term)
    # Kriterium matchspråk (sv, en, ...)
    # Kriterium matchplats (term, annan plats)
    # Kriterium matchkvalitet (exakt, annan match)
    # Kriterium sorteringsterm (alfabetiskt)
    matches = list(filter(lambda x: x["type"] != "canonical",
                          match(term.get("terms", []), searchStringExpressions)))
    matchlangprio = min([term_lang_prio.get(e["match"]["lang"], 100) for e in matches] + [100])
    matchquality = min([matchquality_prio.get(e["type"], 100) for e in matches] + [100])
    sorteringsterm = [e["text"].lower().replace("-", " ") for e in matches]
    # Kriterium källa (efter år, sedan titel, sedan utgivare)
    if term["kalla"].get("year"):
        try:
            year = -int(term["kalla"]["year"])
        except ValueError:
            year = 0
    else:
        year = 0
    kalla = KallaSortKey(
        year,
        term["kalla"].get("title") or "",
        term["kalla"].get("publisher") or "",
    )
    # Kriterium homonymnummer
    # XXX should sort homonym number together with term
    homonymnummer = [e["match"].get("homonym", 0) for e in matches]
    # Kriterium definition/förklaring (alfabetiskt)
    # Kriterium lankterm (alfabetiskt)
#    print("matches", matches)
#    print("sortering", (matches,matchlangprio,matchquality,sorteringsterm,kalla,homonymnummer))
    tiebreak_terms = [get_term_text(e) for e in sorted(term.get("terms", []), key=lambda x: (term_lang_prio.get(x["lang"], 100), term_prio.get(x["status"], 100), x.get("term", "")))]
    return TermSortKey(matchlangprio,matchquality,sorteringsterm,kalla,homonymnummer,tiebreak_terms)

text_type_prio = {
    "definition": 0,
    "explanation": 1,
}


def text_sortkey(text):
    type_prio = text_type_prio.get(text["type"], 100)
    lang_prio = term_lang_prio.get(text["lang"], 100)
    return TextPrioKey(type_prio, lang_prio)

@bp.app_template_filter('staticfile')
def staticfile_hash(filename):
    return "static/" + filename

import collections

db = client.rikstermbanken

from pymongo.collation import Collation

class RegexSearchStringExpression(NamedTuple):
    pythonregex: Any
    bsonregex: Regex
    @classmethod
    def create(cls, s):
        bsonregex = glob_to_regex(s)
        pythonregex = glob_to_regex(s, pythonstyle=True)
        return cls(pythonregex=pythonregex, bsonregex=bsonregex)
    def mongodbsearchversion(self):
        return self.bsonregex
    def isString(self):
        return False
    def matches(self, s):
        return self.pythonregex.match(s) is not None
    def matchesAny(self, l):
        return any([self.matches(e) for e in l])

class StringSearchStringExpression(NamedTuple):
    string: str
    def mongodbsearchversion(self):
        return self.string
    def isString(self):
        return True
    def casefold(self):
        return self.string.casefold()
    def matches(self, s):
        return s.casefold() == self.string.casefold()
    def matchesAny(self, l):
        return any([self.matches(e) for e in l])

@bp.app_template_filter('matchesany')
def matchesany(word, expressions):
    return any([e.matches(word) for e in expressions])

def glob_to_regex(s, pythonstyle=False):
    escaped = ""
    for c in s:
        if c == "*":
            escaped += ".*"
        elif c == "?":
            escaped += "."
        else:
            if pythonstyle:
                escaped += "\\u%04x" % ord(c)
            else:
                escaped += "\\x{%04x}" % ord(c)
    if pythonstyle:
        return re.compile("^" + escaped + "$", re.IGNORECASE)
    else:
        return Regex("^" + escaped + "$", flags="i")

@bp.route('/simpleSearch.html', methods=['POST'])
def search():
    searchString = request.form["searchString"]
    assert isinstance(searchString, str)
    log_access("/simpleSearch.html", searchString)
    searchString = searchString.strip()
    lang = "sv"
    collation = Collation("sv@collation=search", strength=2)
    searchStringExpressions = []
    for word in searchString.split(" "):
        if "?" in word or "*" in word:
            searchStringExpressions.append(RegexSearchStringExpression.create(word))
        else:
            searchStringExpressions.append(StringSearchStringExpression(word))
    if request.form.get("sokomfattningsval", "termer") == "termer":
        searchfield = "searchterms"
    else:
        searchfield = "fulltextsearch"
    results = sorted(db.termpost.find({
        "kalla.status": 2,
        searchfield: {"$all": [e.mongodbsearchversion() for e in searchStringExpressions]}
        }, collation=collation, limit=1001), key=lambda x: sortkey(x, lang, searchStringExpressions))
    toomany = len(results) > 1000
    if toomany:
        results = []
    more = len(results) > 500
    results = results[:500]
    for result in results:
        result["matches"] = group_match_lang(match(result.get("terms", []), searchStringExpressions))
        result["priotext"] = sorted(filter(lambda x: text_sortkey(x).type < 100,
                                           result.get("texts", [])),
                                    key=text_sortkey)
        result["sortkey"] = sortkey(result, lang, searchStringExpressions)
    return render_template('rtb_results.html', results=results, searchStringExpressions=searchStringExpressions, current="search", more=more, toomany=toomany)

iftexts = {
    "term":{
        "sg":{
            "rec": markupsafe.Markup("term&nbsp;(rekommenderad)"),
            "std": "term",
            "acc": markupsafe.Markup("term&nbsp;(accepterad)"),
            "dep": "term\u00a0(avr\u00e5dd)",
            "inf": markupsafe.Markup("term&nbsp;(uttydning)"),
        },
        "pl":{
            "rec": markupsafe.Markup("termer&nbsp;(rekommenderade)"),
            "std": "termer",
            "acc": markupsafe.Markup("termer&nbsp;(accepterade)"),
            "dep": markupsafe.Markup("termer&nbsp;(avr\u00e5dda)"),
            "inf": markupsafe.Markup("termer&nbsp;(uttydning)"),
        },
    },
    "phrase":{
        "sg":{
            "rec": markupsafe.Markup("fras&nbsp;(rekommenderad)"),
            "std": "fras",
            "acc": markupsafe.Markup("fras&nbsp;(accepterad)"),
            "dep": "fras\u00a0(avr\u00e5dd)",
        },
        "pl":{
            "rec": markupsafe.Markup("fraser&nbsp;(rekommenderade)"),
            "std": "fraser",
            "acc": markupsafe.Markup("fraser&nbsp;(accepterade)"),
            "dep": markupsafe.Markup("fraser&nbsp;(avr\u00e5dda)"),
        },
    },
    "formula":{
        "sg":{
            "rec": markupsafe.Markup("beteckning/formel&nbsp;(rekommenderad)"),
            "std": "beteckning/formel",
            "acc": markupsafe.Markup("beteckning/formel&nbsp;(accepterad)"),
            "dep": "beteckning/formel\u00a0(avr\u00e5dd)",
        },
        "pl":{
            "rec": markupsafe.Markup("beteckningar/formler&nbsp;(rekommenderade)"),
            "std": "beteckningar/formler",
            "acc": markupsafe.Markup("beteckningar/formler&nbsp;(accepterade)"),
            "dep": markupsafe.Markup("beteckningar/formler&nbsp;(avr\u00e5dda)"),
        },
    },
    "lang":{
        "sg":{
        "sv": "svensk",
        "en": "engelsk",
        "de": "tysk",
        "fr": "fransk",
        "es": "spansk",
        "ca": "katalansk",
        "no": "norsk",
        "nb": "norsk\u00a0(bokm\u00e5l)",
        "nn": "nynorsk",
        "da": "dansk",
        "fi": "finsk",
        "fit": "me\u00e4nkielisk",
        "se": "nordsamisk",
        "is": "isl\u00e4ndsk",
        "ru": "rysk",
        "et": "estnisk",
        "ja": "japansk",
        "hr": "bosn./kroat./serb.",
        "pl": "polsk",
        "gr": "grekisk",
        "tr": "turkisk",
        "ku": "kurdisk",
        "fo": "f\u00e4r\u00f6isk",
        "kl": "gr\u00f6nl\u00e4ndsk",
        "la": "latinsk",
        "ar": "arabisk",
        "so": "somalisk",
        "rom": "romsk",
        "sw": "swahilisk",
        "cs": "tjeckisk",
        "mt": "maltesisk",
        "sk": "slovakisk",
        "sl": "slovensk",
        "bg": "bulgarisk",
        "ro": "rum\u00e4nsk",
        "gl": "galicisk",
        "kr": "kroatisk",
        "it": "italiensk",
        "sq": "albansk",
        "rm": "romsk\u00a0(arli)",
        "rk": "romsk\u00a0(kelderasch)",
        "ra": "romsk\u00a0(arli)",
        "re": "lang.re.adj1", # XXX
        "nl": "nederl\u00e4ndsk",
        "pt": "portugisisk",
        "il": "lang.il.adj1", # XXX
        },
        "pl":{
        "sv": "svenska",
        "en": "engelska",
        "de": "tyska",
        "fr": "franska",
        "es": "spanska",
        "ca": "katalanska",
        "no": "norska",
        "nb": "norska\u00a0(bokm\u00e5l)",
        "nn": "nynorska",
        "da": "danska",
        "fi": "finska",
        "fit": "me\u00e4nkieliska",
        "se": "nordsamiska",
        "is": "isl\u00e4ndska",
        "ru": "ryska",
        "et": "estniska",
        "ja": "japanska",
        "hr": "bosn./kroat./serb.",
        "pl": "polska",
        "gr": "grekiska",
        "tr": "turkiska",
        "ku": "kurdiska",
        "fo": "f\u00e4r\u00f6iska",
        "kl": "gr\u00f6nl\u00e4ndska",
        "la": "latinska",
        "ar": "arabiska",
        "so": "somaliska",
        "rom": "romska",
        "sw": "swahiliska",
        "cs": "tjeckiska",
        "mt": "maltesiska",
        "sk": "slovakiska",
        "sl": "slovenska",
        "bg": "bulgariska",
        "ro": "rum\u00e4nska",
        "gl": "galiciska",
        "kr": "kroatiska",
        "it": "italienska",
        "sq": "albanska",
        "rm": "romska\u00a0(arli)",
        "rk": "romska\u00a0(kelderasch)",
        "ra": "romska\u00a0(arli)",
        "re": "lang.re.adj1", # XXX
        "nl": "nederl\u00e4ndska",
        "pt": "portugisiska",
        "il": "lang.il.adj1", # XXX
        },
    },
    "texttype": {
        "comment":"anm\u00e4rkning",
        "equivalence":"ekvivalensanm\u00e4rkning",
        "internanm":"internanm\u00e4rkning",
        "example":"exempel",
        "context":"kontext",
        "definition":"definition",
        "source":"k\u00e4lla",
        "classification":"klassifikation",
        "domain":"anv\u00e4ndningsomr\u00e5de",
        "refterm":"K\u00e4lla",
        "explanation":"f\u00f6rklaring",
        "seealso":"se \u00e4ven",
        "inkorpterm":"inkorporerad term",
        "seeunder":"se vidare under",
        "illustration":"illustrationer",
        "plain": "klarspr\u00e5kskommentar",
    },
    "textmisc": {
        "abbreviation": "f\u00f6rkortning",
        "fullform": "of\u00f6rkortad form",
    },
    "illustration":{
        "illustration":"illustration",
        "concept diagram":"begreppsdiagram",
    },
}

def make_sortorder(l):
    return {v:i for i, v in enumerate(l)}

class ViewType(NamedTuple):
    level: str
    termtype: str

sortorder_termtype = make_sortorder([
   ViewType("rec", "term"), ViewType("std", "term"), ViewType("acc", "term"), ViewType("dep", "term"), ViewType("inf", "term"),
   ViewType("rec", "phrase"), ViewType("std", "phrase"), ViewType("acc", "phrase"), ViewType("dep", "phrase"),
   ViewType("rec", "formula"), ViewType("std", "formula"), ViewType("acc", "formula"), ViewType("dep", "formula"),
                                         ])
sortorder_texttype = make_sortorder(["domain", "context", "definition", "explanation", "comment"])

def term_type(term):
    if term.get("phrase", False):
        term_or_phrase = "phrase"
    else:
        term_or_phrase = "term"
    if term.get("split", False):
        if term["status"] == "TE":
            return ViewType("rec", term_or_phrase)
        elif term["status"] == "BT":
            return ViewType("rec", "formula")
        elif term["status"] == "SYTE":
            return ViewType("acc", term_or_phrase)
    if term["status"] in ["TE", "SYTE"]:
        return ViewType("std", term_or_phrase)
    elif term["status"] == "BT":
        return ViewType("std", "formula")
    elif term["status"] == "AVTE":
        return ViewType("dep", term_or_phrase)
    elif term["status"] == "INTE":
        return ViewType("inf", "term")
    else:
        return ViewType("std", term_or_phrase) # XXX
    
def groupby(l, key):
    groups = []
    for key, group in itertools.groupby(sorted(l, key=key), key):
        groups.append({"key":key, "group": list(group)})
    return groups

def collect_language(termpost, language_code):
    terms = [term for term in termpost.get("terms", []) if term["lang"] == language_code]
    for term in terms:
        term["viewtype"] = term_type(term)
    grouped_terms = groupby(terms, lambda x: x["viewtype"])
    grouped_terms = sorted(grouped_terms, key=lambda x: sortorder_termtype.get(x["key"], 100))
    texts = [text for text in termpost.get("texts", []) if text["lang"] == language_code]
    texts = sorted(texts, key=lambda x: sortorder_texttype.get(x["type"], 100))
    result = {"termgroups":grouped_terms, "texts":texts, "lang": language_code}
    return result

def lookup_term(entry, kalla_id):
    term = entry["term"]
    homonym = entry.get("homonym")
    lang = entry["lang"]
    if homonym:
        search = {"term":term, "homonym":homonym, "lang": lang, "status": "TE"}
    else:
        search = {"term":term, "homonym":{"$exists":False}, "lang": lang, "status": "TE"}
    return db.termpost.find_one({"terms":{"$elemMatch":search}, "kalla.id":kalla_id})

@bp.route('/visaTermpost.html', methods=['GET'])
def show_termpost_old():
    try:
        id = int(request.args.get("id"))
    except (ValueError, TypeError):
        return render_template('termpost_404.html'), 404
    log_access("/visaTermpost.html", id)
    lang = "sv"
    termpost = db.termpost.find_one({
        "id": id,
        })
    return redirect("/termposter/%d/%s" % (termpost["kalla"]["id"], termpost["slugs"][0]))
    
@bp.route('/termposter/<kalla>/<slug>', methods=['GET'])
def show_termpost(kalla, slug):
    log_access("/termposter/", kalla, slug)
    lang = "sv"
    try:
        kalla_id = int(kalla)
    except (ValueError, TypeError):
        return render_template('termpost_404.html'), 404
    termpost = db.termpost.find_one({
        "kalla.id": kalla_id,
        "slugs": slug
        })
    if termpost is None:
        return render_template('termpost_404.html'), 404
    return render_termpost(termpost, 'rtb_termpost.html')

def render_termpost(termpost, template_name):
    seealso = list(filter(None, [lookup_term(e, termpost["kalla"]["id"]) for e in termpost.get("seealso", [])]))
    seeunder = list(filter(None, [lookup_term(e, termpost["kalla"]["id"]) for e in termpost.get("seeunder", [])]))
    terms_langauge_codes = set([term["lang"] for term in termpost.get("terms", [])])
    text_langauge_codes = set([text["lang"] for text in termpost.get("texts", [])])
    language_codes = sort_lang_codes(terms_langauge_codes | text_langauge_codes)
    languages = [collect_language(termpost, language_code) for language_code in language_codes]
    termname = {"term":""}
    if languages:
        termgroups = languages[0].get("termgroups", [])
        if termgroups:
            group = termgroups[0].get("group", [])
            if group:
                termname = group[0]
    illustrations = termpost.get("ILLU", [])
    classifications = termpost.get("classifications", [])
    return render_template(template_name,
                                   languages=languages,
                                   seealso=seealso,
                                   seeunder=seeunder,
                                   illustrations=illustrations,
                                   termpostid=termpost.get("id"),
                                   kalla=termpost["kalla"],
                                   iftexts=iftexts,
                                   termname=termname,
                                   classifications=classifications,
                                       current="termpost")

from comparison import compare

@bp_login.route('/admin/', methods=['GET'])
def show_admin():
    compare_result = compare(db, client.rikstermbanken_staging)
    if compare_result:
        diffs, other_errors, gitversion = compare_result
        return render_template('rb_admin.html', diffs=diffs, other_errors=other_errors, gitversion=gitversion) 
    else:
        return render_template('rb_admin_wait.html')

@bp_login.route('/admin/publish', methods=['POST'])
def publish_source():
    source_id = int(request.form["kallid"])
    intented_gitversion = request.form["gitversion"]
    import_status = client.rikstermbanken_staging.status.find_one({"key":"import"})
    if not import_status:
        return render_template('rb_admin_publish_fail.html')
    imported_gitversion = import_status["gitversion"]
    if imported_gitversion != intented_gitversion:
        return render_template('rb_admin_publish_fail.html')
    source = client.rikstermbanken_staging.kalla.find_one({"id":source_id}, {"_id": False})
    if not source:
        return render_template('rb_admin_publish_fail.html')
    if source["gitversion"] != intented_gitversion:
        return render_template('rb_admin_publish_fail.html')
    termposts = list(client.rikstermbanken_staging.termpost.find({"kalla.id":source_id}, {"_id": False}))
    if len(termposts) == 0:
        return render_template('rb_admin_publish_fail.html')
    for termpost in termposts:
        if termpost["gitversion"] != intented_gitversion:
            return render_template('rb_admin_publish_fail.html')
    client.rikstermbanken.kalla.replace_one({"id":source_id}, source, upsert=True)
    client.rikstermbanken.termpost.delete_many({"kalla.id":source_id})
    client.rikstermbanken.termpost.insert_many(termposts)
    return redirect("/admin/")

@bp.route('/update-hook', methods=['POST'])
def update_hook():
    with open(admincfg.UPDATE_HOOK_FILE, "wt") as f:
        pass # Only touch file
    return ""

import re
from markupsafe import Markup

@bp.app_template_filter('termpost_render')
def termpost_render_filter(source_id, slug):
    termpost = client.rikstermbanken_staging.termpost.find_one({
        "kalla.id": source_id,
        "slugs": slug
        })
    if termpost is None:
        return ""
    return Markup(render_termpost(termpost, 'rtb_termpost_render.html'))

def should_escape(c):
    o = ord(c)
    if o == 0x2013:
        return False
    if o == 0x111:
        return False
    return o >= 128

# XXX remove before delivering to maintenance
@bp.app_template_filter('escapeall')
def escapeall(s):
    if hasattr(s, "__html__"):
        return Markup(s.__html__())
    if s is None:
        return ""
    html_escaped = str(s).replace("&", "&amp;").replace(">", "&gt;").replace("<", "&lt;").replace("'", "&#39;").replace('"', "&#34;")
    html_escaped = "".join(["&#x%X;" % (ord(c),) if should_escape(c) else c for c in html_escaped])
    return Markup(html_escaped)

import json

@bp.app_template_filter('jsonify')
def jsonify(jsonobj):
    return json.dumps(jsonobj, ensure_ascii=False, sort_keys=True)

from pprint import pprint

@bp.route('/static/<subdir>/<filename>')
def static_files_subdir(subdir, filename):
    return send_from_directory("static/", subdir + "/" + filename)

@bp.route('/static/<filename>')
def static_files(filename):
    return send_from_directory("static/", filename)

@bp_debug.route('/all-termpost-ids', methods=['GET'])
def all_termpost_ids():
    results = [e["id"] for e in db.termpost.find({"kalla.status": 2}, projection={"id": True, "_id": False})]
    return jsonify(results)

@bp_debug.route('/all-slugs', methods=['GET'])
def all_slugs():
    results = [{"kalla": e["kalla"]["id"], "slug": e["slugs"][0]} for e in db.termpost.find({"kalla.status": 2}, projection={"kalla.id": True, "slugs": True, "_id": False})]
    return jsonify(results)


@bp_login.before_request
def require_login():
    if request.authorization and request.authorization.username == admincfg.ADMIN_USERNAME and request.authorization.password == admincfg.ADMIN_PASSWORD:
        return
    response = Response(status = 401)
    response.headers['WWW-Authenticate'] = 'Basic realm="rikstermbanken.se"'
    return response

app = Flask(__name__)
app.config.from_pyfile('rikstermbanken.cfg')
app.config['MONGO_CONNECT'] = False
babel = Babel(app)
app.register_blueprint(bp)
app.register_blueprint(bp_login)

app.jinja_env.filters['quote_plus'] = lambda u: quote_plus(u.encode("utf-8"))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.context_processor
def context_processor():
    return {"version": RIKSTERMBANKEN_WEB_VERSION}

if __name__ == '__main__':
#    from werkzeug.middleware.profiler import ProfilerMiddleware
#    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, profile_dir="profiledir")
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
#    @app.before_request
#    def before_request():
#        g.start = time.time()
#    @app.teardown_request
#    def teardown_request(exception=None):
#        diff = time.time() - g.start
#        print("process time", diff)
    app.register_blueprint(bp_debug)
    app.run()

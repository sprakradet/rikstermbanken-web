import collections
import sys
from import_util import textconvert_annotated_term

slug_replacements = {
    " ": "_",
    "\u00a0": "_",
    "'": "-",
    "’": "-",
    '"': "",
    '”': "",
    "%": "procent",
    "&": "-ampersand-",
    "/": "-",
    ":": "-",
    "§": "-paragraf-",
    "–": "-",
    "—": "-",
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
    "⁺": "+",
    "⁻": "-",
    "⁼": "=",
    "⁽": "(",
    "⁾": ")",
    "ⁿ": "n",
    "₀": "0",
    "₁": "1",
    "₂": "2",
    "₃": "3",
	"₄": "4",
    "₅": "5",
    "₆": "6",
    "₇": "7",
    "₈": "8",
    "₉": "9",
	"₊": "+",
	"₋": "-",
	"₌": "=",
	"₍": "(",
	"₎": ")",
    "ₐ": "a",
	"ₑ": "e",
	"ₒ": "o",
    "ₓ": "x",
}

def get_term_term(term):
    if "term" in term:
        s = term["term"]
    elif "annotated_term" in term:
        s = textconvert_annotated_term(term["annotated_term"])
    else:
        assert False, term
    if "\u2029" in s:
        s = s[:s.index("\u2029")]
    for old, new in slug_replacements.items():
        s = s.replace(old, new)
    if "homonym" in term:
        s += "-%d" % (term["homonym"],)
    if term["lang"] != "sv":
        s = term["lang"] + "--" + s
    return s

def get_slugs(terms):
    language_names = [term["lang"] for term in terms]
    for termtype in ["TE", "BT"]:
        for language_name in ["sv", "en", "fi", "la"]:
            if language_name in language_names:
                langterms = [term for term in terms if term["status"] == termtype and term["lang"] == language_name and term.get("term", "") not in ["-", "–"]]
                #print(termtype, language_name, langterms)
                if not langterms:
                    #print("ingen term", language_name, terms)
                    continue
                return [get_term_term(term) for term in langterms]
    if terms == []:
        return []
    print(language_names, terms, file=sys.stderr)
    raise Exception()

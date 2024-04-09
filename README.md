Rikstermbankens webbgränssnitt
==============================

Teknik
------

* Python 3
* Flask 1
* MongoDB 4

Struktur
--------

Huvuddelen av koden ligger i `rikstermbanken.py`. Templates ligger i
`templates` och statiska filer i `static`.

Första installationen
---------------------

På test- och driftservrar installeras webbgränssnittet i
/var/www/rikstermbanken/src:

```bash
cd /var/www/rikstermbanken
git clone git@github.com:sprakradet/rikstermbanken-web.git
```

Detta kommer att hämta den senast incheckade versionen, vilket normalt
inte är den version som ska driftsättas, så följ instruktionerna
under *Driftsättning* innan applikationen börjar användas.

Pythonpaket behöver också installeras:

```bash
sudo /bin/pip3.6 install flask pymongo flask-babel
```

Om det inte redan är gjort behöver wsgi-filen och static-filerna pekas ut i
apache-konfigurationen, vilket görs av den som installerar webbservern:

```apache
    WSGIScriptAlias / /var/www/rikstermbanken/src/rikstermbanken.wsgi
    Alias "/static/" "/var/www/rikstermbanken/src/static/"

    <Directory /var/www/rikstermbanken>
        <Files rikstermbanken.wsgi>
            Require all granted
        </Files>
    </Directory>

    <Directory /var/www/rikstermbanken/src/static>
        Order allow,deny
        Allow from all
        Header set Cache-Control "max-age=84600, public"
    </Directory>
```

Skapa MongoDB-konto för applikationen. Kommandot för att logga in som användaren `admin` är:

```bash
mongo -u admin
```

Vid MongoDB:s kommandoprompt kör du följande kommandon (i exemplet heter databasen
`rikstermbanken`, och användarnamnet du skapar är `rb`):

```javascript
    use rikstermbanken
    db.createUser(
       {
         user: "rb",
         pwd: "<hitta på ett lösenord>",
		 roles: [ { role: "readWrite", db: "rikstermbanken" }]
	   }
	)
    db.grantRolesToUser("rb", [ { role: "readWrite", db: "rikstermbanken_log" } ])
    db.grantRolesToUser("rb", [ { role: "readWrite", db: "rikstermbanken_staging" } ])
```

Detta ger användaren `rb` rättigheter i
`rikstermbanken`, `rikstermbanken_staging` och `rikstermbanken_log`.

Lösenord skapas lämpligen med kommandot `openssl rand -base64 21`.


Skapa filen `/var/www/rikstermbanken/src/mongodbcfg.py` enligt
följande mall, med samma användarnamn, lösenord och databas som ovan:

```python
    MONGODB_USERNAME = "rb"
    MONGODB_PASSWORD = "<lösenord>"
    MONGODB_DB = "<databasen>"
```

Databasen måste också få ett innehåll. Detta sker genom att läsa in
innehållet från en katalog med termfiler med det verktyg som finns i `rikstermbanken-web`.

Uppdateringsskriptet använder
`/var/www/rikstermbanken/src/updatecfg.py`. Eftersom samma
kontouppgifter gäller här som för webbservern, gör en symbolisk länk
till mongodbcfg.py

```bash
	cd /var/www/rikstermbanken/src/
	ln -s mongodbcfg.py /var/www/rikstermbanken/src/updatecfg.py
```

Hämta innehåll:

```bash
cd /var/www/rikstermbanken
git clone <katalog med termfiler>
```

Skapa filen `/var/www/rikstermbanken/src/admincfg.py` med inloggningsuppgifter till adminsidan:

```python
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="<lägg in ett lösenord här>"
```

Driftsättning
-------------

Detta görs varje gång en ny version ska driftsättas, först på
testservern, och efter testningen är gjord, på samma sätt på driftservern:

```bash
    /var/www/rikstermbanken/src/deploy.sh <tag>
```

där `<tag>` är samma som git-taggen för versionen som ska driftsättas.

Skriptet byter till den valda versionen i git och startar om
webbservern.

Databassökningar och prestanda
------------------------------

För att köra kommandon vid mongo-kommandoprompten på test- eller
driftservern är det lämpligast att så långt som möjligt vara inloggad
som `rb`. Dock saknar den användaren skrivrättigheter, så för att
skapa index behöver man vara inloggad som `admin`. Användaren `rb` får
(om användaren är skapad enligt ovan) bara logga in i databasen
`rikstermbanken`, så kommandot för att starta programmet blir:

```bash
    mongo -u rb rikstermbanken
```

Det görs för närvarande tre olika sökningar i databasen.
Den första söker efter den söksträng (`searchString`) användaren har matat in. Den ser ut så
här i Rikstermbankens pythonkod:

```python
    collation = Collation("sv@collation=search", strength=2)
    results = db.termpost.find({
        "kalla.status": 2,
        "searchterms": searchString
        }, collation=collation)
```
		
Anledningen till att `collation` används är för att göra sökningen
skiftlägesokänslig. Den första parametern till `Collation` är språket,
och att strength är `2` betyder att den inte ska göra skillnad på
skiftläge: [se ICU-dokumentationen](http://userguide.icu-project.org/collation/concepts#TOC-Comparison-Levels).

Samma sökning ser ut så här om man vill göra den vid mongo-kommandoprompten:

```javascript
    db.termpost.find( {
        "kalla.status": 2,
        "searchterms": "<searchString>"
        } ).collation( { locale: "sv@collation=search", strength: 2 } )
```

Genom att lägga till `.pretty()` allra sist så får man utmatningen snyggt formaterad.

För att kontrollera hur lång tid sökningen tar och om indexen används
korrekt kan man lägga på .explain("executionStats"):

```javascript
    db.termpost.find( {
        "kalla.status": 2,
        "searchterms": "<searchString>"
        } ).collation( { locale: "sv@collation=search", strength: 2 } ).explain("executionStats")
```

De intressanta delarna är under avdelningen `executionStats`. Här ett
exempel när vi inte har ett lämpligt index:

```json
	"executionStats" : {
		"executionSuccess" : true,
		"nReturned" : 8,
		"executionTimeMillis" : 263,
		"totalKeysExamined" : 0,
		"totalDocsExamined" : 154122,
		"executionStages" : {
			"stage" : "COLLSCAN",
			"filter" : {
				"$and" : [
					{
						"kalla.status" : {
							"$eq" : 2
						}
					},
					{
						"searchterms" : {
							"$eq" : "e-post"
						}
					}
				]
			},
			"nReturned" : 8,
			"executionTimeMillisEstimate" : 2,
			"works" : 154124,
			"advanced" : 8,
			"needTime" : 154115,
			"needYield" : 0,
			"saveState" : 1204,
			"restoreState" : 1204,
			"isEOF" : 1,
			"direction" : "forward",
			"docsExamined" : 154122
		}
	}
```

Här kan vi se att sökningen tog 263 millisekunder
(`executionTimeMillis`) och att antalet dokument som behövde gås
igenom var 154122 (`totalDocsExamined`). Anledningen till det kan vi
se under `executionStages`, där `stage` är `COLLSCAN` (collection
scan), motsvarande en table scan i SQL.

Vi skapar ett index för den här sökningen:

```javascript
    db.termpost.createIndex({"searchterms":1}, { collation: { locale: "sv@collation=search", strength: 2 } })
```

Här är `searchterms` det fält som ska indexeras, och `collation` är
samma som vi utförde sökningen med ovan. Att det står `1` efter
searchterms betyder att indexet är stigande.

Om det redan finns ett index på searchterms så kan man ta bort det
med:

```javascript
    db.termpost.dropIndex({"searchterms":1})
```

Om vi nu gör om samma sökning igen får vi följande resultat:

```json
	"executionStats" : {
		"executionSuccess" : true,
		"nReturned" : 8,
		"executionTimeMillis" : 9,
		"totalKeysExamined" : 9,
		"totalDocsExamined" : 9,
		"executionStages" : {
			"stage" : "FETCH",
			"filter" : {
				"kalla.status" : {
					"$eq" : 2
				}
			},
			"nReturned" : 8,
			"executionTimeMillisEstimate" : 0,
			"works" : 10,
			"advanced" : 8,
			"needTime" : 1,
			"needYield" : 0,
			"saveState" : 0,
			"restoreState" : 0,
			"isEOF" : 1,
			"docsExamined" : 9,
			"alreadyHasObj" : 0,
			"inputStage" : {
				"stage" : "IXSCAN",
				"nReturned" : 9,
				"executionTimeMillisEstimate" : 0,
				"works" : 10,
				"advanced" : 9,
				"needTime" : 0,
				"needYield" : 0,
				"saveState" : 0,
				"restoreState" : 0,
				"isEOF" : 1,
				"keyPattern" : {
					"searchterms" : 1
				},
				"indexName" : "searchterms_1",
				"collation" : {
					"locale" : "sv@collation=search",
					"caseLevel" : false,
					"caseFirst" : "off",
					"strength" : 2,
					"numericOrdering" : false,
					"alternate" : "non-ignorable",
					"maxVariable" : "punct",
					"normalization" : true,
					"backwards" : false,
					"version" : "57.1"
				},
				"isMultiKey" : true,
				"multiKeyPaths" : {
					"searchterms" : [
						"searchterms"
					]
				},
				"isUnique" : false,
				"isSparse" : false,
				"isPartial" : false,
				"indexVersion" : 2,
				"direction" : "forward",
				"indexBounds" : {
					"searchterms" : [
						"[\"1\u0005\u000eGEMO\u0001\n\", \"1\u0005\u000eGEMO\u0001\n\"]"
					]
				},
				"keysExamined" : 9,
				"seeks" : 1,
				"dupsTested" : 9,
				"dupsDropped" : 0
			}
		}
	}
```

Nu tog det istället 9 millisekunder, och totalt 9 dokument gicks igenom.

En annan sökning som görs är för att hitta en specifik termpost. I
Rikstermbankens pythonkod ser den ut så här:

```javascript
    termpost = db.termpost.find_one({
        "id": id,
        })
```

Motsvarande mongo-kommandovariant blir:

```javascript
    db.termpost.findOne({id: <termpostid>})
```

För att den här sökningen ska gå snabbt behövs detta index:

```javascript
    db.termpost.createIndex({"id":1})
```

Till sist har vi en sökning för att hitta vilket termpostid en länkad
term (seealso, seeunder) har givet termen, källan och ett eventuellt homonymnummer:

```python
    if homonym:
        search = {"term":term, "homonym":homonym}
    else:
        search = {"term":term, "homonym":{"$exists":False}}
    return db.termpost.find_one({"terms":{"$elemMatch":search}, "kalla.id":kalla_id})
```

Sökningen görs bland termpostens alla termer. Om homonyminformationen
inte hade varit viktig hade sökningen kunnat se ut så här:

```javascript
    db.termpost.findOne( { "terms.term": "<term>", "kalla.id": "<källaid>" } )
```

Men eftersom det kan finnas flera termer, och det inte räcker med att
termsträngen stämmer med en term och homonymnumret med en annan så
måste de matchas samtidigt:

```javascript
    db.termpost.findOne( { "terms": {
        "$elemMatch": {
	        "term": "<term>",
            "homonym": "<homonym>"
        }
    }, "kalla.id": "<källaid>" } )
```

eller om homonymnumret inte ska finnas:

```javascript
    db.termpost.findOne( { "terms": {
        "$elemMatch": {
	        "term": "<term>",
            "homonym": { "$exists" : False }
        }
    }, "kalla.id": "<källaid>" } )
```


import requests
import json
import re

LANGUAGES = ["ru", "en", "uk", "kk", "es"]
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_ACTION_API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "RafsWikidataBot/0.1 (contact: kislyakhelp@gmail.com | github: https://github.com/ivanKislyak/Rafs | website: https://rafs.app/)"
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT
}

def fetch_movie_raw(qid: str) -> dict:
    if not qid.startswith("Q") or not qid[1:].isdigit():
        raise ValueError("qid is an invalid value")

    query_string = f"""
        SELECT ?movie ?label_ru ?desc_ru ?label_en ?desc_en ?label_uk ?desc_uk ?label_kk ?desc_kk ?label_es ?desc_es 
        WHERE {{
            VALUES ?movie {{ wd:{qid} }}
            
            OPTIONAL {{
                ?movie rdfs:label ?label_ru .
                FILTER(LANG(?label_ru) = "ru")
            }}
            OPTIONAL {{
                ?movie schema:description ?desc_ru .
                FILTER(LANG(?desc_ru) = "ru")
            }}

            OPTIONAL {{ 
                ?movie rdfs:label ?label_en . 
                FILTER(LANG(?label_en) = "en") 
            }}
            OPTIONAL {{ 
                ?movie schema:description ?desc_en . 
                FILTER(LANG(?desc_en) = "en")
            }}

            OPTIONAL {{ 
                ?movie rdfs:label ?label_uk . 
                FILTER(LANG(?label_uk) = "uk") 
            }}
            OPTIONAL {{ 
                ?movie schema:description ?desc_uk . 
                FILTER(LANG(?desc_uk) = "uk")
            }}

            OPTIONAL {{ 
                ?movie rdfs:label ?label_kk . 
                FILTER(LANG(?label_kk) = "kk") 
            }}
            OPTIONAL {{ 
                ?movie schema:description ?desc_kk . 
                FILTER(LANG(?desc_kk) = "kk")
            }}

            OPTIONAL {{ 
                ?movie rdfs:label ?label_es . 
                FILTER(LANG(?label_es) = "es") 
            }}
            OPTIONAL {{ 
                ?movie schema:description ?desc_es . 
                FILTER(LANG(?desc_es) = "es")
            }}
        }}
    """
    params = {
        "query": query_string,
        "format": "json",
    }

    r = requests.get(WIKIDATA_SPARQL_URL, params=params, headers=DEFAULT_HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def fetch_movie_details_raw(qid: str) -> dict:
    if not qid.startswith("Q") or not qid[1:].isdigit():
        raise ValueError("qid is an invalid value")

    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "labels|descriptions|claims",
        "languages": "en|ru|uk|kk|es",
        "format": "json",
    }

    r = requests.get(WIKIDATA_ACTION_API_URL, params=params, headers=DEFAULT_HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def parse_movie_details(raw_details: dict, qid: str) -> dict:
    details_info = raw_details.get("entities", {}).get(qid)
    if not details_info:
        raise ValueError("details have invalid id value")

    labels = details_info.get("labels", {})
    descriptions = details_info.get("descriptions", {})
    claims = details_info.get("claims", {})

    wikidata_name = {lang: value["value"] 
                     for lang, value 
                     in labels.items()
                     if labels}

    wikidata_description = {lang: value["value"].capitalize()
                     for lang, value 
                     in descriptions.items()
                     if descriptions}

    def extract_single_string(claim_id: str) -> str | None:
        if prop_claims := claims.get(claim_id):
            return prop_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
        return None

    def extract_single_qid(claim_id: str, type_of_value: str="id") -> str | None:
        if prop_claims := claims.get(claim_id):
            return prop_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get(type_of_value)
        return None
    
    def extract_dicts(claim_id: str) -> set:
        if prop_claims := claims.get(claim_id):
            return {
                q_id for claim in prop_claims
                if (q_id := claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id"))
            }
        return set()

    parsed_data = {
        "wikidata_id": qid,
        "imdb_id": extract_single_string("P345"),
        "year": int(val[1:5]) if (val := (extract_single_qid("P577", "time") or extract_single_qid("P580", "time"))) else None,
        "wikidata_name": wikidata_name,
        "wikidata_description": wikidata_description,
        "type_of_work": extract_single_qid("P31"),
        "genres": extract_dicts("P136"),
        "countries": extract_dicts("P495"),
        "studio": extract_dicts("P272"),
        "actors": extract_dicts("P161") | extract_dicts("P725"),
        "director": extract_dicts("P57"),
        "producer": extract_dicts("P162"),
        "screenwriter": extract_dicts("P58"),
        "composer": extract_dicts("P86"),
    }
    return parsed_data


def parse_movie_data(raw_data: dict) -> dict:
    bindings = raw_data["results"]["bindings"]
    if not bindings:
        raise ValueError("Фильм с таким QID не найден")

    binding = bindings[0]
    movie_uri = binding["movie"]["value"]
    wikidata_id = movie_uri.rsplit("/", 1)[-1]

    wikidata_name = {}
    wikidata_description = {}

    for lang in LANGUAGES:
        if label := binding.get(f'label_{lang}'): wikidata_name[lang] = label['value']
        if desc := binding.get(f'desc_{lang}'): wikidata_description[lang] = desc['value']

    return {
        "wikidata_id": wikidata_id,
        "wikidata_name": wikidata_name,
        "wikidata_description": wikidata_description,
    }

def search_wikidata_media(query: str, lang="ru", limit=10) -> list[dict]:
    query = re.sub(r'["\'«»]', '', query)
    query = query.strip()
    if not query:
        raise ValueError("Для поиска нужно ввести название произведения")

    if lang not in LANGUAGES:
        raise ValueError("Неподдерживаемый язык")
        
    limit = int(limit)
    if not 1 <= limit <= 20:
        raise ValueError("limit должен быть от 1 до 20")

    query_literal = json.dumps(query, ensure_ascii=False)

    sparql_query = f"""
    SELECT DISTINCT ?item ?itemLabel ?itemDescription ?ordinal WHERE {{
      # Поиск по текстовому совпадению названия с внутренним лимитом в 50
      SERVICE wikibase:mwapi {{
        bd:serviceParam wikibase:api "EntitySearch" .
        bd:serviceParam wikibase:endpoint "www.wikidata.org" .
        bd:serviceParam mwapi:search {query_literal} .
        bd:serviceParam mwapi:language "{lang}" .
        ?item wikibase:apiOutputItem mwapi:item .
        ?ordinal wikibase:apiOrdinal true .
        bd:serviceParam wikibase:limit 50 .
      }}
      
      # Фильтрация: сущность должна быть фильмом/сериалом ИЛИ их подклассом (аниме, мультфильм и т.д.)
      VALUES ?root_type {{
        wd:Q11424     # film
        wd:Q5398426   # television series
      }}
      ?item wdt:P31/wdt:P279* ?root_type .
      
      # Получение подписей и описаний на нужном языке
      SERVICE wikibase:label {{ 
        bd:serviceParam wikibase:language "{lang},en" . 
      }}
    }}
    ORDER BY ASC(?ordinal)
    LIMIT {limit}
    """

    params = {
        "query": sparql_query,
        "format": "json"
    }

    response = requests.get(WIKIDATA_SPARQL_URL, params=params, headers=DEFAULT_HEADERS, timeout=15)
    response.raise_for_status()
    
    data = response.json()
    results = []
    
    for row in data.get("results", {}).get("bindings", []):
        wikidata_url = row.get("item", {}).get("value", "")
        wikidata_id = wikidata_url.split("/")[-1] if wikidata_url else None
        
        results.append({
            "id": wikidata_id,
            "title": row.get("itemLabel", {}).get("value", ""),
            "description": row.get("itemDescription", {}).get("value", "").capitalize()
        })
        
    return results
import requests

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

    # try:
    # data = fetch_movie_raw("Q123")
    # movies = data["results"]["bindings"]
    # except requests.exceptions.HTTPError as httpError:
    #     return {"Error": "http_error", "details": str(httpError)}

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

def search_wikidata_entities_raw(query: str, lang="ru", limit=5) -> dict:
    if not query.strip():
        raise ValueError("Для поиска нужно ввести название фильма")

    limit_str = str(int(limit))

    sparql_query = f"""
    SELECT DISTINCT ?item ?itemLabel ?itemDescription WHERE {{
      # Поиск по текстовому совпадению названия
      SERVICE wikibase:mwapi {{
        bd:serviceParam wikibase:api "EntitySearch" .
        bd:serviceParam wikibase:endpoint "www.wikidata.org" .
        bd:serviceParam mwapi:search "{query}" .
        bd:serviceParam mwapi:language "{lang}" .
        ?item wikibase:apiOutputItem mwapi:item .
      }}
      
      # Фильтрация: сущность должна быть экземпляром (P31) одного из медиа-классов
      ?item wdt:P31 ?type .
      VALUES ?type {{
        wd:Q11424     # Фильм (film)
        wd:Q5398426   # Телесериал (television series)
        wd:Q267241    # Аниме-сериал (anime television series)
        wd:Q1107      # Аниме (anime)
        wd:Q202866    # Анимационный фильм / Мультфильм (animated film)
        wd:Q581714    # Анимационный сериал / Мультсериал (animated television series)
      }}
      
      # Получение подписей и описаний на нужном языке
      SERVICE wikibase:label {{ 
        bd:serviceParam wikibase:language "{lang},en" . 
      }}
    }}
    LIMIT {limit_str}
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
            "description": row.get("itemDescription", {}).get("value", "Нет описания")
        })
        
    return results
import requests

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_SEARCH_ENDPOINT = "https://wikidata.org/w/api.php"
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

    r = requests.get(WIKIDATA_SEARCH_ENDPOINT, params=params, headers=DEFAULT_HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()
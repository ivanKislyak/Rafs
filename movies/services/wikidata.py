import requests

def fetch_movie_raw(qid: str) -> dict:
    if qid.startswith("Q") and qid[1:].isdigit():
        url = "https://query.wikidata.org/sparql"

        queryString = f"""
            SELECT ?movie ?movieLabel ?movieDescription
            WHERE {{
                VALUES ?movie {{ wd:{qid} }}

                SERVICE wikibase:label {{
                    bd:serviceParam wikibase:language "ru,en".
                }}
        }}
        """
        params = {
            "query": queryString,
            "format": "json",
        }

        headers = {
            "User-Agent": "rafs-app/0.5 (contact: kislyakhelp@gmail.com | github: https://github.com/ivanKislyak/Rafs | website: https://rafs.app/) Python/3.11 Requests/2.31.0"
        }

        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as httpError:
            return {"Error": "http_error", "details": str(httpError)}
        except Exception as error:
            return {"Error": "network_error", "details": str(error)}
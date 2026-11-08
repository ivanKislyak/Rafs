from celery import shared_task
from celery.utils.log import get_task_logger
from .services.wikidata import fetch_movie_details_raw

logger = get_task_logger(__name__)

@shared_task(ignore_result=True)
def check_wikidata_movie(qid: str):
    payload = fetch_movie_details_raw(qid)
    entities = payload["entities"]
    
    if qid not in entities:
        logger.warning("Warning! Missed Q-ID(%s)" % qid)
        return

    movie_data = entities.get(qid, {})

    if "missing" in movie_data:
        logger.warning("Warning! A missing key. Q-ID: %s" % qid)
        return

    title = movie_data.get("labels", {}).get("en", {}).get("value", qid)
    logger.info("qid=%s title=%s" % (qid, title))
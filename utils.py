import re
import emoji
import discord
import typing as t

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConflictError
from datetime import datetime, timedelta, timezone

from logger import log
from constants import (
    ELASTICSEARCH_HOST,
    ELASTICSEARCH_PORT,
    INDEX_NAME,
    TYPE_NAME,
    HISTORICAL_RUN_START_DATE as HRSD,
    SCRAPING_UPDATES_INTERVAL,
    SCRAPING_HISTORY_INTERVAL
)


es = Elasticsearch([{"host": ELASTICSEARCH_HOST, "port": ELASTICSEARCH_PORT}], timeout=30, scheme={})


# ====================== Clients + Connections ======================
def es_client_init() -> Elasticsearch:
    return Elasticsearch([{
        "host": ELASTICSEARCH_HOST,
        "port": ELASTICSEARCH_PORT,
    }], timeout=30, scheme={})


# ====================== ES requests/queries/parsers ======================
async def write_to_es(
    es: Elasticsearch,
    message_id: str,
    message: t.Dict[t.Union[str, t.Any], t.Union[list, t.Any]],
    index_name: str = INDEX_NAME
) -> None:
    try:
        es.index(index=index_name, doc_type=TYPE_NAME, id=message_id, body=message)
    except Exception as e:
        log.error(f"Failed to write tweet {message_id} from {message['sender_username']} to ES: {e}")


def _parse_time_field(time_field: t.Union[str, int]) -> datetime:
    if isinstance(time_field, int) or (isinstance(time_field, str) and time_field.isdigit()):
        return datetime.fromtimestamp(int(time_field) // 1000, tz=timezone.utc).replace(tzinfo=None)
    else:
        try:
            return datetime.strptime(time_field.split('+')[0], '%Y-%m-%dT%H:%M:%S.%f')
        except Exception as e:
            log.error(f'Error parse time field: {time_field}')
            raise e


def _get_last_msg_in_es_dt(channel_id: int) -> t.Optional[datetime]:
    query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "match": {
                                    "channel_id": f"{channel_id}"
                                }
                            }
                        ]
                    }
                },
                "sort": {
                    "timestamp": "desc"
                },
                "size": 1
            }

    try:
        last_msg = es.search(index=INDEX_NAME, body=query)
        if last_msg:
            raw_last_dt = last_msg['hits']['hits'][0]['_source']['timestamp']
            last_dt = _parse_time_field(raw_last_dt)
            return last_dt
    except IndexError:
        log.warning(f'Error parsing last ES doc time field, apparently table is empty',
                    extra={"channel_id": f"{channel_id}"})
        # return _round_dt_to_5min(datetime.utcnow() - timedelta(seconds=SCRAPING_HISTORY_INTERVAL))
        return None
    except Exception as e:
        log.warning(f'Error parsing last ES doc time field, but nevermind: {e}',
                    extra={"channel_id": f"{channel_id}"})
        return None


def _round_dt_to_5min(dt: datetime) -> datetime:
    return dt - timedelta(
        minutes=dt.minute % 5,
        seconds=dt.second,
        microseconds=dt.microsecond
    )


def calculate_dt_from(channel_id: t.Optional[int] = None) -> datetime:
    """
    function to calculate start date for history collecting
    """
    dt_to = _round_dt_to_5min(datetime.utcnow())
    dt_from = dt_to - timedelta(seconds=SCRAPING_UPDATES_INTERVAL)
    if channel_id:  # True for collecting history, False for collecting updates
        _last_msg_in_es_dt = _get_last_msg_in_es_dt(channel_id)
        log.info(f'Last message in ES index {INDEX_NAME} is for {_last_msg_in_es_dt}',
                 extra={"channel_id": f"{channel_id}"})
        # in case of empty index or explicitly set datetime to start history collection from
        dt_from = HRSD if HRSD else dt_to - timedelta(seconds=SCRAPING_HISTORY_INTERVAL)
        if _last_msg_in_es_dt:
            # choose max() date to not collect the hole history again in case of regular k8s restarts
            dt_from = max(_last_msg_in_es_dt, dt_from)
        log.info(f'Final {dt_from=}',
                 extra={"channel_id": f"{channel_id}"})
    return dt_from


# ====================== Parse message to ES format ======================
async def process_message(message) -> t.Tuple[str, t.Dict[t.Union[str, t.Any], t.Union[list, t.Any]]]:

    _channel = message.channel
    _thread = None
    if hasattr(message.channel, 'parent'):  # message is in thread
        _channel = message.channel.parent
        _thread = message.channel

    _message = dict()
    try:
        _message = {
             'message_id': message.id,
             'server_name': message.guild.name,
             'server_id': message.guild.id,
             'sender_id': message.author.id,
             'sender_username': message.author.name,
             'sender_display_name': message.author.display_name,
             'sender_is_bot': message.author.bot,
             'sender_roles': [_.name for _ in message.author.roles] if isinstance(message.author, discord.Member) else [],
             'channel_id': _channel.id,
             'channel_title': _channel.name,
             'channel_category': _channel.category.name if _channel.category else None,
             'channel_category_id': _channel.category_id,
             'thread_id': _thread.id if _thread else None,
             'thread_title': _thread.name if _thread else None,
             'thread_category': _thread.category.name if _thread and _thread.category else None,
             'thread_category_id': _thread.category_id if _thread else None,
             'text': message.content,
             'raw_text': message.clean_content if hasattr(message, "clean_content") else "",
             'emoji_list': [emoji.EMOJI_DATA[_]['en'] for _ in emoji.distinct_emoji_list(message.content)],
             'emoji_img_list': [_ for _ in emoji.distinct_emoji_list(message.content)],
             'cashtag_list': re.findall(r'\${1}\b([a-zA-Z]{2,})', message.content),
             'timestamp': message.created_at,
             'computed_at': datetime.utcnow(),
             'is_reply': True if message.type.name == 'reply' else False,
             'reply_to_msg': message.reference.message_id if message.reference else None,
             'mentions': message.raw_mentions,
             'reactions_dict': {emoji.EMOJI_DATA[_.emoji]['en']: _.count for _ in message.reactions if isinstance(_.emoji, str)},  # don't process super reactions objects
             'reactions_img_dict': {_.emoji: _.count for _ in message.reactions if isinstance(_.emoji, str)},  # don't process super reactions objects
             'media': [a.url for a in message.attachments] if message.attachments else []
             }
    except Exception as e:
        # this zone is dangerous, because script could stack here
        log.warning(f"Exception while process message {message.id}: {e}",
                    extra={"channel_id": f"{message.channel.id}"})
    return message.id, _message

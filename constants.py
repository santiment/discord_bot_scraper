import typing as t

from os import getenv
from datetime import datetime
from logger import log

from dotenv import load_dotenv

load_dotenv()


def __history_datetime_setter(_history_datetime: str) -> t.Union[str, datetime]:
    history_datetime = ''
    try:
        if _history_datetime:
            history_datetime = datetime.strptime(_history_datetime, '%Y-%m-%dT%H:%M:%S')
    except ValueError as e:
        log.error(f'Error while parsing HISTORY_DATETIME: {e}')
    except Exception as e:
        log.error(f'Exception while setting HISTORY_DATETIME: {e}')
    finally:
        return history_datetime


def __bot_token_setter(_bot_token: str) -> str:
    if not _bot_token:
        raise ValueError(f'BOT_TOKEN is empty. Stop script')
    else:
        return _bot_token


def __guild_setter(_guild: str) -> str:
    if not _guild:
        raise ValueError(f'GUILD is empty. Stop script')
    else:
        return _guild


def __channels_setter(_channels: str) -> list:
    # CHANNELS shouldn't be empty to not collect and store all msgs from all server channels including possible trash
    channels = list()
    if not _channels:
        raise ValueError(f'CHANNELS is empty. Stop script')
    for channel_id in set(_channels.split(',')):
        try:
            channels.append(int(channel_id))
        except ValueError as e:
            log.error(f'Error while parsing CHANNELS: {e}. Stop script')
            raise
        except Exception as e:
            log.error(f'Exception while setting CHANNELS: {e}. Stop script')
            raise
    return channels


SCRAPING_HISTORY_INTERVAL = 86400
SCRAPING_UPDATES_INTERVAL = 300
QUEUE_SIZE_MULTIPLIER = 100
MESSAGE_BATCH_SIZE = 1000

HEALTH_CHECK_INTERVAL = getenv('HEALTH_CHECK_INTERVAL', "")

INDEX_NAME = getenv('INDEX', "")

ELASTICSEARCH_HOST = getenv('ELASTICSEARCH_HOST', "")
ELASTICSEARCH_PORT = int(getenv('ELASTICSEARCH_PORT', ""))

HISTORICAL_RUN_START_DATE = __history_datetime_setter(getenv('HISTORICAL_RUN_START_DATE', ""))

BOT_TOKEN = __bot_token_setter(getenv('BOT_TOKEN', ""))
GUILD = __guild_setter(getenv('GUILD', ""))
CHANNELS = __channels_setter(getenv('CHANNELS', ""))

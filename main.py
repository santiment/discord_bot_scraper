import time
import discord
import asyncio
import threading
import typing as t

from flask import Flask
from elasticsearch import Elasticsearch, helpers
from elasticsearch.helpers.errors import BulkIndexError
from prometheus_client import Gauge, make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from logger import log
from utils import calculate_dt_from, process_message, es_client_init, write_to_es
from constants import (
    GUILD,
    HEALTH_CHECK_INTERVAL,
    ELASTICSEARCH_HOST,
    ELASTICSEARCH_PORT,
    INDEX_NAME,
    TYPE_NAME,
    MESSAGE_BATCH_SIZE,
    SCRAPING_UPDATES_INTERVAL,
    QUEUE_SIZE_MULTIPLIER,
    CHANNELS,
    BOT_TOKEN
)

app = Flask(__name__)
# Add prometheus wsgi middleware to route `/metrics` requests
app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {'/metrics': make_wsgi_app()})
ES_DISCORD_NEW_DOCS_NUMBER = Gauge('es_discord_new_docs_number',  # metric name
                                   'number of new messages over a HEALTH_CHECK_INTERVAL period',  # description
                                   ['guild'])  # labels


@app.route('/health_check')
def health_check():
    query = {
      "query": {
        "bool": {
          "must": [
            {
              "match_phrase": {
                "server_name.keyword": f"{GUILD}"
              }
            },
            {
              "range": {
                "timestamp": {
                  "gte": f"now-{HEALTH_CHECK_INTERVAL}",
                  "lte": "now"
                }
              }
            }
          ]
        }
      }
    }
    es = Elasticsearch([{'host': ELASTICSEARCH_HOST, 'port': ELASTICSEARCH_PORT}])

    size = es.search(index=INDEX_NAME, body=query).get('hits').get('total').get('value')
    ES_DISCORD_NEW_DOCS_NUMBER.labels(GUILD).set(0 if size is None else size)
    if size in [0, None]:
        return f'Error! {size} documents found. Restart the scraper.', 500
    else:
        return f'Ok, {size} documents found', 200


async def _collect_unread_from_channels(
    client: discord.client.Client,
    es: Elasticsearch,
    channels: t.Dict[int, str],
    _history: bool = False
) -> None:
    """
    collect actual history messages from channels
    :param _history: affects history horizon
                    True = collects long-term history for SCRAPING_HISTORY_INTERVAL
                    False = collects short-term history(aka updates) for SCRAPING_UPDATE_INTERVAL
    """
    async def __looping_through_messages(_channel, _dt_from) -> int:
        _counter, _messages = 0, list()
        # impossible to get number of unread messages to set as limit
        async for message in _channel.history(limit=None, after=_dt_from):
            _message_id, _message = await process_message(message)
            _messages.append({"_index": INDEX_NAME, "_type": TYPE_NAME, '_op_type': 'index', "_id": _message_id, "_source": _message})
            _counter += 1
            if _counter % MESSAGE_BATCH_SIZE == 0:
                try:
                    helpers.bulk(es, _messages)
                except BulkIndexError:
                    pass
                finally:
                    _messages = list()

        try:
            helpers.bulk(es, _messages)
        except BulkIndexError:
            pass

        return _counter

    for channel_id in channels:
        counter = 0
        dt_from = calculate_dt_from(channel_id) if _history else calculate_dt_from()
        channel = client.get_channel(channel_id)
        try:
            if type(channel) is not discord.channel.ForumChannel:
                counter = await __looping_through_messages(channel, dt_from)
            # collecting history from threads in the channel, threads can be thought of as temporary sub-channels
            for thread in channel.threads:
                counter += await __looping_through_messages(thread, dt_from)
        except discord.Forbidden as e:
            log.error(f'Forbidden to access channel message history: {e}',
                      extra={"channel_id": f"{channel_id}"})
        except Exception as e:
            log.error(f'Exception while collecting unread messages from channel: {e}',
                      extra={"channel_id": f"{channel_id}"})
        finally:
            if _history:
                log.info(f'Collected {counter} history messages from channel',
                         extra={"channel_id": f"{channel_id}"})


async def collect_history(client: discord.client.Client, channels: t.Dict[int, str]) -> None:
    """
    history collector, history is for last SCRAPING_HISTORY_INTERVAL; serves to collect longer history horizon;
    also comes in handy to catch message we possibly lost in streaming during restarts
    """
    log.info('Start collecting history')
    es = es_client_init()
    await _collect_unread_from_channels(client, es, channels, _history=True)


async def collect_updates(client: discord.client.Client, channels: t.Dict[int, str]) -> None:
    """
    collect a “history” constantly in loop; serves to collect shorter history horizon:
    every SCRAPING_UPDATES_INTERVAL seconds it collects messages from previous
    SCRAPING_UPDATES_INTERVAL seconds in loop), thus the same message will be replaced in
    database with updates(useful for updating reactions list and in case the message was edited)
    """
    log.info('Start collecting updates')
    es = es_client_init()
    while True:
        ts_to = int(time.time())
        await _collect_unread_from_channels(client, es, channels)
        ts_to += SCRAPING_UPDATES_INTERVAL
        time_to_sleep = max(ts_to - time.time(), 1)
        await asyncio.sleep(time_to_sleep)


async def stream_channels(client: discord.client.Client, q: asyncio.queues.Queue) -> None:
    """
    function to catch every newly occurred message in every channel;
    channel filtering will be performed later if needed during process message;
    on_message() event catches new messages from threads(newly created/existed) as well
    """
    log.info('Start stream channels')

    @client.event
    async def on_message(message):
        await q.put(message)


async def consumer(
    client: discord.client.Client,
    queue: asyncio.queues.Queue,
    es: Elasticsearch,
) -> None:
    """
    channel filtering and message processing are performed here
    """
    while True:
        message = await queue.get()
        if message is None:  # handle the case of empty queue
            break

        # protection against a potentially recursion in case bot(client.user),
        # writes smth in channel, even though it doesn't - skip those messages
        if message.author != client.user:
            _message_id, _message = await process_message(message)
            await write_to_es(es, _message_id, _message)


async def main():
    """
    starting and setting up the discord client, retrieving guild object and searching for channels;
    launching history collector, streaming and queue consumer coroutines
    """
    channels = dict()

    intents = discord.Intents.default()
    intents.message_content = True  # to get all msg content, not only from bot private msg or via explicit @bot mention
    intents.members = True
    client = discord.Client(intents=intents)

    q = asyncio.Queue(maxsize=len(CHANNELS) * QUEUE_SIZE_MULTIPLIER)
    es = es_client_init()

    @client.event
    async def on_ready():
        log.info(f'Successfully logged in as {client.user}')

        guild = discord.utils.get(client.guilds, name=GUILD)  # search for exact server in case of multiple choice
        log.info(f'Listening to server: {guild.id}')

        for channel in client.get_all_channels():  # search for defined channels
            if channel.id in CHANNELS and type(channel) in [discord.channel.TextChannel, discord.channel.ForumChannel]:
                if channel.guild != guild:  # extra check that channel belongs to the necessary server
                    continue
                channels[channel.id] = channel.name

        # In common case if more channels were found than it stands in input list
        # it means that channel with same name exists in multiple different servers
        log.info(f'Found {len(channels)} channels out of {len(CHANNELS)}: {channels}')
        log.info(f'Missing channels: {set(CHANNELS) - set(channels.keys())}')

        await asyncio.gather(
            collect_history(client, channels),
            collect_updates(client, channels),
            stream_channels(client, q),
            consumer(client, q, es),
        )

    await client.start(BOT_TOKEN)


if __name__ == '__main__':
    threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 5000}).start()

    # t = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 5000})
    # t.daemon = True  # daemon thread with Flask app will be killed as soon as the main program exits
    # t.start()

    start_time = time.time()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
        loop.run_until_complete(loop.shutdown_asyncgens())
    except Exception as e:
        log.error(f'Exception occurred: {e}')
        raise Exception  # to restart script with k8s
    finally:
        loop.close()
        log.info(f'Total script work time={time.time() - start_time}')

import os
import json
import click
import logging

from datetime import datetime
from pythonjsonlogger import jsonlogger


GUILD = os.getenv('GUILD', "")
LOG_LEVEL = int(os.getenv('LOG_LEVEL', 10))
CUSTOM_LOG_FORMAT = os.getenv('LOG_FORMAT', "%(asctime)s %(levelname)s %(guild)s %(channel_id)s %(message)s")
WSGI_LOG_FORMAT = os.getenv('WSGI_LOG_FORMAT', "%(message)s")
RENAME_FIELDS = {"asctime": "time", "levelname": "level"}


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    making regular script logger into json
    """
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)

        # to set default value for a field
        if not log_record.get("guild"):
            log_record["guild"] = GUILD


log = logging.getLogger(__name__)
logHandler = logging.StreamHandler()
logHandler.setFormatter(CustomJsonFormatter(CUSTOM_LOG_FORMAT, rename_fields=RENAME_FIELDS))
log.addHandler(logHandler)
log.setLevel(LOG_LEVEL)


class WSGIJsonFormatter(logging.Formatter):
    """
    making Flask logs into json when /health_checker or /metrics is requested
    """
    def format(self, record: logging.LogRecord) -> str:
        status_code = None
        log_record = super(WSGIJsonFormatter, self).format(record)
        log_record = click.unstyle(log_record)  # disable ansi color codes in message str
        try:
            status_code = int(log_record[-5:-2])
            log_record = log_record.split('\"')[1]
        except:
            pass
        json_result = {
            "guild": f"{GUILD}",
            "message": f"{log_record}",
            "status_code": status_code if status_code else None,
            "time": f"{datetime.now().strftime('%F %T,%f')[:-3]}",
            "level": f"{record.levelname}",
        }
        return json.dumps(json_result)


wsgi_logger = logging.getLogger('werkzeug')
wsgi_logger_handler = logging.StreamHandler()
wsgi_logger_handler.setFormatter(WSGIJsonFormatter(WSGI_LOG_FORMAT))
wsgi_logger.addHandler(wsgi_logger_handler)

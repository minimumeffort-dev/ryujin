import json
import queue

from persistqueue import SQLiteAckQueue
from persistqueue.serializers import json as json_serializer

from paths import QUEUE_DIR


def open_queue():
    return SQLiteAckQueue(
        path=str(QUEUE_DIR), serializer=json_serializer, auto_resume=False
    )


if __name__ == "__main__":
    queue = open_queue()

    try:
        print(json.dumps(queue.queue(), indent=2))
    finally:
        queue.close()

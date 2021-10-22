import time

import requests

from edge.models import Sensory
from edge_repository.settings import settings


def cron_task(function, seconds):
    time.sleep(seconds)
    function()


def send_sensory():
    target_data = Sensory.objects.filter(id__gt=settings['sensory'])

    if len(target_data) > 0:
        settings['sensory'] = target_data[-1].id

        list_of_data = []
        for data in target_data:
            list_of_data.append({'sensorID': data.sensorID, 'value': data.value, 'datetime': data.datetime})

        print(requests.post(settings['cloud_address'] + '/api/sensory/', data=list_of_data).json())


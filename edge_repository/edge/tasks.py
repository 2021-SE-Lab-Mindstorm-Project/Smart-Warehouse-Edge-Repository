import json
import time

import requests

from edge.models import Sensory
from edge_repository.settings import settings


def cron_task(function, seconds):
    time.sleep(seconds)
    function()


def send_sensory():
    target_data = Sensory.objects.filter(uploaded=False)

    if len(target_data) > 0:
        list_of_data = []
        for data in target_data:
            list_of_data.append({'sensorID': data.sensorID, 'value': data.value, 'datetime': str(data.datetime)})
            data.uploaded = True
            data.save()

        json_list = json.dumps(list_of_data)
        headers = {"Content-type": "application/json"}

        requests.post(settings['cloud_address'] + '/api/sensory/', data=json_list, headers=headers)

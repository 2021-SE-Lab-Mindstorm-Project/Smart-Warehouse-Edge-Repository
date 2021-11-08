import datetime
import json

import requests
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, viewsets
from rest_framework.response import Response

from edge_repository.settings import settings
from . import models, rl
from .models import Sensory, Inventory, Order, Message, Status

if int(settings['anomaly_aware']) == 1:
    rl_model = rl.DQN(5, path='../a_rl_r.pth')
else:
    rl_model = rl.DQN(3, path='../rl_r.pth')
anomaly = [False, False]

# Serializer
class SensoryListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        sensory_data_list = [Sensory(**item) for item in validated_data]
        return Sensory.objects.bulk_create(sensory_data_list)


class SensorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Sensory
        fields = '__all__'
        list_serializer_class = SensoryListSerializer


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = '__all__'


# Sensory Data
class SensoryViewSet(viewsets.ModelViewSet):
    queryset = Sensory.objects.all()
    serializer_class = SensorySerializer
    http_method_names = ['post']

    @swagger_auto_schema(responses={400: "Bad Request"})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=isinstance(request.data, list))
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, headers=headers)


def find_best_order():
    state = []
    available = [True] * 4
    for i in range(3):
        stored_items = Inventory.objects.filter(stored=i)
        if len(stored_items) == 0:
            state.append(-1)
            available[i] = False
        else:
            state.append(stored_items[0].item_type)

    if settings['anomaly_aware']:
        state.extend(anomaly)

    tactic = int(rl_model.select_tactic(state, available))
    if tactic == 3:
        return None, None

    item = Inventory.objects.filter(stored=tactic)[0]
    orders = Order.objects.filter(item_type=item.item_type)
    if len(orders) == 0:
        return None, None

    return orders[0], tactic


class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    http_method_names = ['post']
    shipment_capacity = 0
    selected_time = datetime.datetime.now()
    best_order = None
    best_rep = None

    @swagger_auto_schema(
        responses={400: "Bad request", 204: "Invalid Message Title / Invalid Message Sender / Not allowed"})
    def create(self, request, *args, **kwargs):
        super().create(request, *args, **kwargs)
        sender = int(request.data['sender'])
        title = request.data['title']

        if sender == models.MACHINE_REPOSITORY_1 or sender == models.MACHINE_REPOSITORY_2 or sender == models.MACHINE_REPOSITORY_3:
            if title == 'Running Check':
                if len(Status.objects.all()) == 0:
                    return Response("Not allowed", status=204)

                current_status = Status.objects.all()[0]

                if current_status.status:
                    return Response(status=201)

                return Response("Not allowed", status=204)

            if title == 'Sending Check':
                stored = sender - models.MACHINE_REPOSITORY_1 + 1
                first_item = Inventory.objects.filter(stored=stored)[0]

                if self.selected_time + datetime.timedelta(minutes=1) < datetime.datetime.now():
                    self.best_order, self.best_rep = find_best_order()
                    self.selected_time = datetime.datetime.now()

                if self.best_rep is not None and self.best_rep + 1 == stored:
                    if self.shipment_capacity < settings['max_capacity_shipment']:
                        self.shipment_capacity += 1

                        process_message = {'sender': models.EDGE_REPOSITORY,
                                           'title': 'Order Processed',
                                           'msg': json.dumps({'item_type': first_item.item_type,
                                                              'stored': first_item.stored,
                                                              'dest': self.best_order.dest})}
                        requests.post(settings['edge_classification_address'] + '/api/message/', data=process_message)
                        requests.post(settings['cloud_address'] + '/api/message/', data=process_message)

                        self.best_order.delete()
                        self.best_order = None
                        first_item.delete()

                        return Response(status=201)

                return Response("Not allowed", status=204)

            if title == 'Anomaly Occurred':
                location = sender - models.MACHINE_REPOSITORY_1
                if location == 2:
                    location = 1

                anomaly[location] = True

                process_message = {'sender': models.EDGE_REPOSITORY,
                                   'title': 'Anomaly Occurred',
                                   'msg': location}
                requests.post(settings['edge_classification_address'] + '/api/message/', data=process_message)
                requests.post(settings['cloud_address'] + '/api/message/', data=process_message)

                return Response(status=201)

            if title == 'Anomaly Solved':
                location = sender - models.MACHINE_REPOSITORY_1
                if location == 2:
                    location = 1

                anomaly[location] = False

                process_message = {'sender': models.EDGE_REPOSITORY,
                                   'title': 'Anomaly Solved',
                                   'msg': location}
                requests.post(settings['edge_classification_address'] + '/api/message/', data=process_message)
                requests.post(settings['cloud_address'] + '/api/message/', data=process_message)

                return Response(status=201)

            return Response("Invalid Message Title", status=204)

        if sender == models.EDGE_CLASSIFICATION:
            if title == 'Classification Processed':
                msg = json.loads(request.data['msg'])
                item_type = int(msg['item_type'])
                stored = int(msg['stored'])

                # Modify Inventory DB
                target_item = Inventory(item_type=item_type, stored=stored)
                target_item.save()

                return Response(status=201)

            return Response("Invalid Message Title", status=204)

        if sender == models.EDGE_SHIPMENT:
            if title == 'Order Processed':
                self.shipment_capacity -= 1

                return Response(status=201)

            return Response("Invalid Message Title", status=204)

        if sender == models.CLOUD:
            if title == 'Order Created':
                order_data = json.loads(request.data['msg'])
                new_order = Order(item_type=int(order_data['item_type']), made=order_data['made'])
                new_order.save()

                return Response(status=201)

            if title == 'Start':
                Inventory.objects.all().delete()
                Order.objects.all().delete()
                self.shipment_capacity = 0

                if len(Status.objects.all()) == 0:
                    current_state = Status()
                else:
                    current_state = Status.objects.all()[0]

                current_state.status = True
                current_state.save()
                return Response(status=201)

            if title == 'Stop':
                if len(Status.objects.all()) == 0:
                    current_state = Status()
                else:
                    current_state = Status.objects.all()[0]

                current_state.status = False
                current_state.save()
                return Response(status=201)

            return Response("Invalid Message Title", status=204)

        return Response("Invalid Message Sender", status=204)

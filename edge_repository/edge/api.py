import datetime
import json

import requests
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, viewsets
from rest_framework.response import Response

from edge_repository.settings import settings
from . import models
from .models import Sensory, Inventory, Order, Message, Status


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


class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    http_method_names = ['post']

    current_anomaly = [False] * 3
    waited_from = [None] * 3
    recent_order = [None] * 3
    shipment_capacity = 0

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
                stored = sender - models.MACHINE_REPOSITORY_1
                first_item = Inventory.objects.filter(stored=stored)[0]
                target_orders = Order.objects.filter(item_type=first_item.item_type).order_by('made')

                if self.current_anomaly[stored]:
                    return Response("Not allowed", status=204)

                if self.shipment_capacity < settings['max_capacity_shipment']:
                    if len(target_orders) == 0:
                        if self.waited_from[stored] is None:
                            self.waited_from[stored] = datetime.datetime.now()
                            return Response("Not allowed", status=204)

                        if datetime.datetime.now() - self.waited_from[stored] < datetime.timedelta(seconds=10):
                            return Response("Not allowed", status=204)

                    else:
                        target_order = target_orders[0]
                        self.recent_order[stored] = (target_order.item_type, target_order.made)
                        target_order.delete()

                    self.waited_from[stored] = None
                    self.shipment_capacity += 1

                    process_message = {'sender': models.EDGE_REPOSITORY,
                                       'title': 'Order Processed',
                                       'msg': stored}
                    requests.post(settings['edge_classification_address'] + '/api/message/', data=process_message)
                    requests.post(settings['cloud_address'] + '/api/message/', data=process_message)

                    return Response(status=201)

                return Response("Not allowed", status=204)

            if title == 'Anomaly Occurred':
                location = sender - models.MACHINE_REPOSITORY_1
                self.current_anomaly[location] = True
                if self.recent_order[location] is not None:
                    new_order = Order(item_type=self.recent_order[location][0], made=self.recent_order[location][1])
                    new_order.save()

                process_message = {'sender': models.EDGE_REPOSITORY,
                                   'title': 'Anomaly Occurred',
                                   'msg': location}
                requests.post(settings['cloud_address'] + '/api/message/', data=process_message)

                return Response(status=201)

            if title == 'Anomaly Solved':
                location = sender - models.MACHINE_REPOSITORY_1
                self.current_anomaly[location] = False
                self.waited_from[location] = None
                target_orders = Order.objects.filter(item_type=self.recent_order[location][0]).order_by('made')

                if len(target_orders) != 0:
                    target_order = target_orders[0]
                    target_order.delete()

                process_message = {'sender': models.EDGE_REPOSITORY,
                                   'title': 'Anomaly Solved',
                                   'msg': location}
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
                self.waited_from = [None] * 3
                self.recent_order = [None] * 3
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

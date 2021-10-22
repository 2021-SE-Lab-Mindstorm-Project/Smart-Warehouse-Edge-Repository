from datetime import datetime

import requests
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, viewsets
from rest_framework.response import Response

from edge_repository.settings import settings
from . import models
from .models import Sensory, Inventory, Order, Message


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
    orders = Order.objects.all()
    if len(orders) == 0:
        return None

    inventory = Inventory.objects.all()

    i = 0
    while i < len(orders):
        target_item_type = orders[i].item_type
        if inventory[target_item_type - 1].value != 0:
            return orders[i]
        i += 1

    return None


class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    http_method_names = ['post']

    @swagger_auto_schema(responses={400: "Bad request / Invalid Message Title / Invalid Message Sender / Not allowed"})
    def create(self, request, *args, **kwargs):
        super().create(request, *args, **kwargs)
        sender = request.data['sender']
        title = request.data['title']

        if sender == models.MACHINE_REPOSITORY_1 or sender == models.MACHINE_REPOSITORY_2 or sender == models.MACHINE_REPOSITORY_3:
            if title == 'Sending Check':
                item_type = sender - models.MACHINE_REPOSITORY_1 + 1
                target_order = find_best_order()

                if target_order is not None and item_type == target_order.item_type:
                    capacity_check = Inventory.objects.filter(item_type=models.SHIPMENT)[0]
                    if capacity_check.value < settings['max_capacity_shipment']:
                        target_order.delete()

                        capacity_check.value += 1
                        capacity_check.updated = datetime.now()
                        capacity_check.save()

                        item_type = sender - models.MACHINE_REPOSITORY_1 + 1
                        inventory_check = Inventory.objects.filter(item_type=item_type)[0]
                        inventory_check.value -= 1
                        inventory_check.updated = datetime.now()
                        inventory_check.save()

                        process_message = {'sender': models.EDGE_REPOSITORY,
                                           'title': 'Order Processed',
                                           'msg': {'item_type': item_type}}
                        requests.post(settings['edge_classification_address'] + '/api/message/', data=process_message)
                        requests.post(settings['cloud_address'] + '/api/message/', data=process_message)

                        return Response(201)

                return Response({400: "Not allowed"})

            return Response({400: "Invalid Message Title"})

        if sender == models.EDGE_SHIPMENT:
            if title == 'Order Processed':
                capacity_check = Inventory.objects.filter(item_type=models.SHIPMENT)[0]
                capacity_check.value -= 1
                capacity_check.updated = datetime.now()
                capacity_check.save()

                return Response(201)

            return Response({400: "Invalid Message Title"})

        if sender == models.CLOUD:
            if title == 'Order Created':
                msg = request.data['msg']
                new_order = Order(item_type=int(msg['item_type']), made=msg['made'])
                new_order.save()

                return Response(201)

            return Response({400: "Invalid Message Title"})

        return Response({400: "Invalid Message Sender"})

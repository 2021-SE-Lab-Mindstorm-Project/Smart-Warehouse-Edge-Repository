import datetime

from django.db import models

RED = 1
WHITE = 2
YELLOW = 3
SHIPMENT = 0
item_type_choices = [
    (RED, 'Red'),
    (WHITE, 'White'),
    (YELLOW, 'Yellow'),
    (SHIPMENT, 'Shipment')
]

LEFT = 1
MIDDLE = 2
RIGHT = 3
dest_choices = [
    (LEFT, 'Left'),
    (MIDDLE, 'Middle'),
    (RIGHT, 'Right')
]


class Inventory(models.Model):
    item_type = models.IntegerField(choices=item_type_choices)
    value = models.IntegerField()
    updated = models.DateTimeField(auto_now=datetime.datetime.now)


class Order(models.Model):
    made = models.DateTimeField(default=datetime.datetime.now)
    item_type = models.IntegerField(choices=item_type_choices)


class Sensory(models.Model):
    sensorID = models.CharField(max_length=50)
    value = models.FloatField()
    datetime = models.DateTimeField()
    uploaded = models.BooleanField(default=False)


USER = 0
CLOUD = 1
EDGE_CLASSIFICATION = 11
EDGE_REPOSITORY = 12
EDGE_SHIPMENT = 13
MACHINE_CLASSIFICATION = 21
MACHINE_REPOSITORY_1 = 22
MACHINE_REPOSITORY_2 = 23
MACHINE_REPOSITORY_3 = 24
MACHINE_SHIPMENT = 25

sender_choices = [
    (USER, 'User'),
    (CLOUD, 'Cloud'),
    (EDGE_CLASSIFICATION, '[Edge] Classification'),
    (EDGE_REPOSITORY, '[Edge] Repository'),
    (EDGE_SHIPMENT, '[Edge] Shipment'),
    (MACHINE_CLASSIFICATION, '[Machine] Classification'),
    (MACHINE_REPOSITORY_1, '[Machine] Repository-1'),
    (MACHINE_REPOSITORY_2, '[Machine] Repository-2'),
    (MACHINE_REPOSITORY_3, '[Machine] Repository-3'),
    (MACHINE_SHIPMENT, '[Machine] Shipment')
]


class Message(models.Model):
    sender = models.IntegerField(choices=sender_choices)
    title = models.CharField(default='', max_length=50)
    msg = models.TextField(default='', blank=True, null=True)
    datetime = models.DateTimeField(default=datetime.datetime.now)


class Status(models.Model):
    status = models.BooleanField(default=False)
    updated = models.DateTimeField(auto_now=datetime.datetime.now)

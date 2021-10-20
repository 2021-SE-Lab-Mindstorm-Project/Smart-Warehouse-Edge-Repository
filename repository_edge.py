import json
import socket
import threading
import time

settings_file = open("../../settings.json")
settings_data = json.load(settings_file)
settings_file.close()

repository_device = []
edges = []
MAX_CAP = {'red': 10, 'yellow': 10, 'white': 10}
storing = {'red': 0, 'yellow': 0, 'white': 0}
SHIP_MAX_CAP = 10
ship_repository = 0
shipping_queue = []
lock = threading.Lock()
server_connection = object()


class repository_device_connection(threading.Thread):
    def __init__(self, port_num=5004):
        super().__init__()
        self.port_num = port_num
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(("", self.port_num))
        self.client_socket = object()
        self.ack = 0
        self.connection = 0
        print("init done")

    def run(self):
        self.server_socket.listen(5)
        print("port" + str(self.port_num) + " open & listening")
        self.client_socket, self.address = self.server_socket.accept()
        self.connection = 1
        print("I got a connection from ", self.address)
        while 1:
            self.wait_request()

    def wait_request(self):
        global server_connection
        ret = self.client_socket.recv(512).decode()
        ret = json.loads(ret)
        if ret['type'] == "sensor":
            server_connection.log_message(ret)
        elif ret['type'] == "request":
            while 1:
                print("ERROR:double ack from ev3")
                if self.ack == 0:
                    break
            self.ack = 1
        else:
            raise TypeError
        return ret

    def order(self, data):
        if self.connection == 1:
            print("edge->cloud : requesting shipping repository status update: " + str(data))
            data_to_server = {'type': 'request', 'data': data}
            data_to_server = json.dumps(data_to_server)
            self.client_socket.send(data_to_server.encode())
            return True
        else:
            return False

    def disconnect(self):
        # ASSERT(self.connection == 1)
        self.client_socket.close()
        self.connection = 0
        self.server_socket.close()
        print("socket to " + str(self.address) + "disconnected")
        self.exit()


class EtoE_connection(threading.Thread):
    def __init__(self, port_num=5007):
        super().__init__()
        self.port_num = port_num
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(("", self.port_num))
        self.client_socket = object()
        self.connection = 0
        print("init done")

    def run(self):
        self.server_socket.listen(5)
        print("port" + str(self.port_num) + " open & listening")
        self.client_socket, self.address = self.server_socket.accept()
        self.connection = 1
        print("I got a connection from ", self.address)

        # if classification edge -> listen to updates
        if self.port_num == settings_data['repository_edge']['service_port_classification']:
            while 1:
                self.repository_update()
        # if shipping edge -> listen to repository update
        elif self.port_num == settings_data['repository_edge']['service_port_shipment']:
            while 1:
                self.ship_repository_update()

    def repository_update(self):
        # communicate with ev3, update "storing" & "item_update" variable
        global storing
        lego = self.receive()
        lock.acquire()
        storing[lego] += 1
        lock.release()
        print("repository update " + lego + ": " + str(storing[lego] - 1) + "->" + str(storing[lego]))

    def ship_repository_update(self):
        global ship_repository
        data = edges[1].receive()
        if (data == 'True'):
            lock.acquire()
            ship_repository -= 1
            lock.release()
            print("shipping repository update: " + str(ship_repository + 1) + "->" + str(ship_repository))

    def notice(self, data):
        if self.connection == 1:
            self.client_socket.send(data.encode())
            return True
        else:
            print("Error: Edge not connected!")
            return False

    def receive(self):
        ret = self.client_socket.recv(512).decode()
        return ret

    def disconnect(self):
        # ASSERT(self.connection == 1)
        self.client_socket.close()
        self.connection = 0
        self.server_socket.close()
        print("socket to " + str(self.address) + "disconnected")
        self.exit()


class connect_to_server(threading.Thread):
    def __init__(self, port_num=27000):
        super().__init__()
        self.port_num = port_num
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connection = 0
        print("init done")

    def run(self):
        self.client_socket.connect((settings_data['cloud']['address'], self.port_num))
        self.connection = 1
        global server_connection
        print("connected to server")
        while 1:
            lego = self.wait_command()
            self.req_release(lego)
            time.sleep(0.1)

    def req_release(self, data):
        global ship_repository
        global storing
        global repository_device
        global lock
        print('Cloud->edge: release request ' + str(data))

        global shipping_queue
        shipping_queue.extend(data)
        shipped = []
        # data format : [color1, color2, ...]
        # check repository -> order -> wait -> empty_cap--

        for req in shipping_queue:
            # lock.acquire()
            repository_no = (storing[req] == 0)
            ship_repository_no = ((SHIP_MAX_CAP - ship_repository) == 0)
            # lock.release()
            if repository_no:
                print(str(req) + " not available in repository.. skip to next order")
            elif ship_repository_no:
                print("no room for more shipment.. waiting for more room")
                break
            else:
                color = 0
                if req == 'red':
                    color = 0
                elif req == 'white':
                    color = 1
                elif req == 'yellow':
                    color = 2

                shipping_queue.remove(req)
                shipped.append(req)
                repository_device[color].order('True')
                while 1:
                    if repository_device[color].ack == 1:
                        repository_device[color].ack = 0
                        break
                edges[0].notice(req)
                # lock.acquire()
                ship_repository += 1
                # lock.release()
                print("shipping " + str(req))
                print("shipping repository update: " + str(ship_repository + 1) + "->" + str(ship_repository))

        print(" - request order report --")
        print("|ordered: " + str(data))
        print("|shipped: " + str(shipped))
        print("|remaining " + str(shipping_queue))
        print(" -------------------------")
        self.message(shipped)

    def wait_command(self):
        ret = self.client_socket.recv(512).decode()
        ret = json.loads(ret)
        return ret

    def message(self, data):
        print("edge->cloud : requesting shipping status update: " + str(data))
        data_to_server = {'type': 'request', 'data': data}
        data_to_server = json.dumps(data_to_server)
        self.client_socket.send(data_to_server.encode())

    def log_message(self, data):
        print("edge->cloud : log " + str(data))
        data_to_server = {'type': 'sensor', 'data': data}
        data_to_server = json.dumps(data_to_server)
        self.client_socket.send(data_to_server.encode())


def init():
    global server_connection
    # connect to cloud
    server_connection = connect_to_server(settings_data['cloud']['service_port_repository'])
    server_connection.start()

    # open server for 3 repository ev3
    global repository_device
    for i in [settings_data['repository_edge']['service_port_0'], settings_data['repository_edge']['service_port_0'],
              settings_data['repository_edge']['service_port_0']]:
        new_repository = repository_device_connection(i)
        new_repository.start()
        repository_device.append(new_repository)

    # open server for 2 other edges
    # edge 0 : classification edge , edge 1: shipping edge
    for i in [settings_data['repository_edge']['service_port_classification'],
              settings_data['repository_edge']['service_port_shipment']]:
        new_edge = EtoE_connection(i)
        new_edge.start()
        edges.append(new_edge)

    print("waiting for order...")
    server_connection.join()
    for i in range(3):
        repository_device[i].join()
    for i in range(2):
        edges[i].join()
    print("end of the code")


if __name__ == '__main__':
    init()

# sio.emit('update_sensor_db', [{'time_stamp': 1, 'ev3_id': 'repository', 'sensor_type':'color', 'value':0xFF0000}])
# sio.emit('item_released',{'red':10, 'white':2, 'yellow':3})

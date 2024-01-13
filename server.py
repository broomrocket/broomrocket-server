import abc
import json
import pprint
import socket
import struct
import threading
import typing
import uuid
from abc import ABC
from concurrent.futures import ThreadPoolExecutor

import broomrocket
from broomrocket import LoadedMesh, GLTF, BroomrocketLogger, Broomrocket, Volume


class SocketLoadedMesh(LoadedMesh):
    """
    This mesh holds the data received over the socket.
    """

    _name: str
    _size: broomrocket.Volume
    _translation: typing.ForwardRef("SocketCoordinate")
    message_handler: typing.ForwardRef("MessageHandler")

    def __init__(self, message_handler: typing.ForwardRef("MessageHandler"), name: str, size: broomrocket.Volume,
                 translation: typing.ForwardRef("SocketCoordinate")):
        self._name = name
        self._size = size
        self._translation = translation
        self.message_handler = message_handler
        translation.change_callback = self._translation_changed

    @property
    def name(self) -> str:
        return self._name

    @property
    def size(self) -> Volume:
        return self._size

    def get_size_submesh_fallback(self, name: str) -> broomrocket.Volume:
        return self.size

    @classmethod
    def from_dict(
            cls,
            message_handler: typing.ForwardRef("MessageHandler"),
            data: typing.Dict
    ) -> typing.ForwardRef("SocketLoadedMesh"):
        return cls(
            message_handler,
            data["name"],
            broomrocket.Volume.from_dict(data["volume"]),
            SocketCoordinate.from_dict(data["translation"])
        )

    def _translation_changed(self):
        self.message_handler.send_request({
            "command": "move_mesh",
            "name": self.name,
            "translation": self.translation.to_dict()
        })

    @property
    def translation(self) -> broomrocket.Coordinate:
        """
        Translation returns the coordinate of the root/pivot point of the mesh. The returned coordinate must, when
        changed, translate those changes back to the mesh even when the setter below is not called explicitly.
        """
        return self._translation

    @translation.setter
    def translation(self, translation: broomrocket.Coordinate):
        """
        This setter moves the mesh to have its root/pivot point to the specified coordinates.
        """
        self._translation = SocketCoordinate(
            translation.x,
            translation.y,
            translation.z
        )
        self._translation.change_callback = self._translation_changed
        self._translation_changed()


class MessageWriter(abc.ABC):
    @abc.abstractmethod
    def send(self, message):
        pass


class MessageReader(abc.ABC):
    @abc.abstractmethod
    def read_next(self):
        pass


class SocketEngine(broomrocket.Engine):
    """
    This is the engine implementation for a client communicating over a socket.
    """

    message_handler: typing.ForwardRef("MessageHandler")

    def __init__(self, message_handler: typing.ForwardRef("MessageHandler")):
        self.message_handler = message_handler

    def load_gltf(self, name: str, data: GLTF, logger: BroomrocketLogger) -> LoadedMesh:
        response = self.message_handler.send_request({
            "command": "load_gltf",
            "name": name,
            "gltf": data.to_dict()
        })
        return SocketLoadedMesh.from_dict(self.message_handler, response["object"])

    def list_objects(self) -> typing.List[LoadedMesh]:
        response = self.message_handler.send_request({
            "command": "list_objects"
        })
        result = []
        for obj in response["objects"]:
            result.append(SocketLoadedMesh.from_dict(self.message_handler, obj))
        return result


class SocketCoordinate(broomrocket.Coordinate):
    _x: float
    _y: float
    _z: float

    change_callback: typing.Callable

    def __init__(self, x: float, y: float, z: float):
        self._x = x
        self._y = y
        self._z = z

    @property
    def x(self) -> float:
        return self._x

    @x.setter
    def x(self, x: float):
        self._x = x
        if self.change_callback is not None:
            self.change_callback()

    @property
    def y(self) -> float:
        return self._y

    @y.setter
    def y(self, y: float):
        self._y = y
        if self.change_callback is not None:
            self.change_callback()

    @property
    def z(self) -> float:
        return self._z

    @z.setter
    def z(self, z: float):
        self._z = z
        if self.change_callback is not None:
            self.change_callback()

    @classmethod
    def from_dict(cls, param: typing.Dict[str, float]) -> broomrocket.Coordinate:
        return SocketCoordinate(param["x"], param["y"], param["z"])

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z
        }


class MessageHandler:
    broomrocket: Broomrocket

    def __init__(self, message_writer: MessageWriter, message_reader: MessageReader):
        self.message_queue = {}
        self.message_writer = message_writer
        self.message_reader = message_reader

        self.broomrocket = broomrocket.Broomrocket(
            SocketEngine(self),
            [
                broomrocket.DummyMeshProvider(),
                broomrocket.LocalMeshProvider(),
                broomrocket.SketchfabMeshProvider()
            ],
            broomrocket.SpaCyNLPProvider(),
            [
                broomrocket.NamedReferenceFinder()
            ],
            [
                broomrocket.BehindPlacementStrategy(),
                broomrocket.FrontPlacementStrategy(),
                broomrocket.LeftPlacementStrategy(),
                broomrocket.RightPlacementStrategy(),
                broomrocket.AbovePlacementStrategy(),
                broomrocket.OnPlacementStrategy(),
                broomrocket.UnderPlacementStrategy(),
                broomrocket.NoPlacementStrategy()
            ],
        )

    def send_request(self, data):
        message_id = str(uuid.uuid4())
        self.message_writer.send({
            "type": "request",
            "id": message_id,
            "data": data
        })
        return self.message_reader.read_next()["data"]

    def on_request(self, message):
        try:
            self.broomrocket.run(
                message["data"]["mesh_provider_id"],
                message["data"]["mesh_provider_parameters"],
                message["data"]["sentence"],
                broomrocket.PythonLogger()
            )
            self.message_writer.send({
                "type": "response",
                "id": message["id"],
                "data": {"status": "ok", "message": "Executed successfully."}
            })
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            self.message_writer.send({
                "type": "response",
                "id": message["id"],
                "data": {"status": "error", "message": str(e)}
            })


class ClientHandler(threading.Thread, MessageWriter, MessageReader):
    client_socket: socket.socket
    message_handler: MessageHandler

    def __init__(self, client_ip, client_port, client_socket):
        threading.Thread.__init__(self)
        self.client_socket = client_socket
        self.message_handler = MessageHandler(self, self)

    def run(self):
        try:
            self.message_handler.on_request(self.read_next())
        finally:
            self.client_socket.close()

    def send(self, message):
        msg = json.dumps(message)
        self.client_socket.send(struct.pack("<l", len(msg)))
        self.client_socket.send(msg.encode())

    def read_next(self):
        data = self.client_socket.recv(4)
        if len(data) < 4:
            self.client_socket.close()
            return
        [message_length] = struct.unpack("<l", data)
        message_data: bytes = b""
        while len(message_data) < message_length:
            message_data += self.client_socket.recv(message_length - len(message_data))
        print(message_data.decode())
        message = json.loads(message_data)
        return message


def main():
    host = "127.0.0.1"
    port = 3333

    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen_sock.bind((host, port))

    listen_sock.listen()
    threads = []

    try:
        while True:
            (client_socket, (ip, port)) = listen_sock.accept()
            client_handler = ClientHandler(ip, port, client_socket)
            client_handler.start()
            threads.append(client_handler)
    finally:
        for thread in threads:
            thread.join()


if __name__ == "__main__":
    main()

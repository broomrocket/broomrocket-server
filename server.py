import abc
import asyncio
import dataclasses
import json
import socket
import struct
import threading
import typing
import uuid
from abc import ABC

import broomrocket
from broomrocket import LoadedMesh, GLTF, BroomrocketLogger, Broomrocket


@dataclasses.dataclass
class SocketLoadedMesh(LoadedMesh):
    """
    This mesh holds the data received over the socket.
    """
    name: str
    size: broomrocket.Volume
    translation: broomrocket.Coordinate

    def get_size_submesh_fallback(self, name: str) -> broomrocket.Volume:
        return self.size

    @classmethod
    def from_dict(cls, data: dict) -> typing.ForwardRef("SocketLoadedMesh"):
        return cls(
            data["name"],
            broomrocket.Volume.from_dict(data["size"]),
            broomrocket.Coordinate.from_dict(data["translation"])
        )


class MessageWriter(abc.ABC):
    @abc.abstractmethod
    def send(self, message):
        pass


class SocketEngine(broomrocket.Engine):
    """
    This is the engine implementation for a client communicating over a socket.
    """

    message_writer: MessageWriter

    def __init__(self, message_writer: MessageWriter):
        self.message_writer = message_writer

    def load_gltf(self, name: str, data: GLTF, logger: BroomrocketLogger) -> LoadedMesh:
        response = self.message_writer.send({
            "command": "load_gltf",
            "name": name,
            "gltf": data.to_dict()
        })
        return SocketLoadedMesh.from_dict(response)

    def list_objects(self) -> typing.List[LoadedMesh]:
        response = self.message_writer.send({"command": "list_objects"})
        result = []
        for obj in response:
            result.append(SocketLoadedMesh.from_dict(obj))
        return result


class Responder(abc.ABC):
    @abc.abstractmethod
    def respond(self, data):
        pass


class MessageHandler:
    broomrocket: Broomrocket
    message_queue: typing.Dict[str, asyncio.Future]

    def __init__(self, message_writer: MessageWriter):
        self.message_writer = message_writer

        self.broomrocket = broomrocket.Broomrocket(
            SocketEngine(message_writer),
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

    async def send(self, data):
        message_id = str(uuid.UUID())
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self.message_queue[message_id] = fut
        self.message_writer.send({
            "type": "request",
            "id": message_id,
            "data": data
        })
        await fut
        return fut.result()

    def on_message(self, message):
        # TODO error handling
        if message["type"] == "request":
            try:
                self.broomrocket.run(
                    message["data"]["mesh_provider_id"],
                    message["data"]["mesh_provider_parameters"],
                    message["data"]["sentence"],
                    broomrocket.PythonLogger()
                )
                self.message_writer.send({
                    "type": "request",
                    "id": message["id"],
                    "data": {"status": "ok", "message": "Executed successfully."}
                })
            except Exception as e:
                self.message_writer.send({
                    "type": "request",
                    "id": message["id"],
                    "data": {"status": "error", "message": str(e)}
                })
        else:
            self.message_queue[message["id"]].set_result(message["data"])
            del self.message_queue[message["id"]]


class ClientHandler(threading.Thread, Responder, MessageWriter, ABC):
    client_socket: socket.socket
    message_handler: MessageHandler

    def __init__(self, client_ip, client_port, client_socket):
        threading.Thread.__init__(self)
        self.client_socket = client_socket
        self.message_handler = MessageHandler(self)

    def run(self):
        [message_length] = struct.unpack("<l", self.client_socket.recv(4))
        finished = False
        messagedata: bytes = b""
        while not finished:
            messagedata += self.client_socket.recv(message_length - len(messagedata))
        message = json.loads(messagedata)
        self.message_handler.on_message(message)

    def send(self, message):
        msg = json.dumps(message)
        self.client_socket.send(struct.pack("<l", len(msg)))
        self.client_socket.send(msg.encode())


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

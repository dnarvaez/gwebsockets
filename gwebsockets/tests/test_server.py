import unittest

from twisted.internet import gtk3reactor
gtk3reactor.install()

from gi.repository import GLib
from twisted.internet import reactor
from autobahn.websocket import WebSocketClientFactory
from autobahn.websocket import WebSocketClientProtocol
from autobahn.websocket import connectWS

from gwebsockets.server import Server


class Protocol(WebSocketClientProtocol):
    def onOpen(self):
        self.sendMessage("Hello, world!")

    def onMessage(self, message, binary):
        reactor.stop()


class Client:
    def __init__(self, port):
        factory = WebSocketClientFactory("ws://localhost:%d" % port)
        factory.protocol = Protocol
        connectWS(factory)

    def start(self):
        reactor.run()


class TestServer(unittest.TestCase):
    def test_send_message(self):
        def message_received_cb(session, message):
            session.send_message(message.data)

        def session_started_cb(server, session):
            session.connect("message-received", message_received_cb)

        server = Server()
        server.connect("session-started", session_started_cb)
        port = server.start()

        client = Client(port)
        client.start()

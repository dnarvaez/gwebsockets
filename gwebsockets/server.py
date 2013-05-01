# Copyright 2013 Daniel Narvaez
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from StringIO import StringIO

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject

from gwebsockets import protocol


class MessageBuffer():
    def __init__(self):
        self._data = b""
        self._cursor = 0
        self.available = 0

    def append(self, data):
        self._data = self._data + data
        self._update_available()

    def read(self, size):
        result = self._data[self._cursor:self._cursor + size]
       
        self._cursor = self._cursor + size
        self._update_available()

        return result

    def _update_available(self):
        self.available = len(self._data) - self._cursor


class Message():
    TYPE_TEXT = 0
    TYPE_BINARY = 1

    def __init__(self, message_type, data):
        self.message_type = message_type
        self.data = data


class Session(GObject.GObject):
    message_received = GObject.Signal("message-received", arg_types=(object,))

    def __init__(self, connection):
        GObject.GObject.__init__(self)

        self._connection = connection
        self._request = StringIO()
        self._message = MessageBuffer()
        self._parse_g = None
        self._ready = False

    def _response_write_cb(self, stream, result, user_data):
        stream.write_bytes_finish(result)
        self._ready = True

    def _do_handshake(self):
        self._request.seek(0)
        response = protocol.make_handshake(self._request)

        stream = self._connection.get_output_stream()
        stream.write_bytes_async(GLib.Bytes.new(response.encode("utf-8")),
                                 GLib.PRIORITY_DEFAULT,
                                 None, self._response_write_cb, None)

    def got_data(self):
        stream = self._connection.get_input_stream()
        data = stream.read_bytes(8192, None).get_data()

        if self._ready:
            if self._message is None:
                self._message = MessageBuffer()

            self._message.append(data)

            if self._parse_g is None:
                self._parse_g = protocol.parse_message(self._message)

            parsed_message = self._parse_g.next()
            if parsed_message:
                self._parse_g = None
                self._message = None

                if parsed_message.tp == protocol.OPCODE_TEXT:
                    message = Message(Message.TYPE_TEXT, parsed_message.data)
                elif parsed_message.tp == protocol.OPCODE_BINARY:
                    message = Message(Message.TYPE_BINARY, parsed_message.data)

                self.message_received.emit(message)
        else:
            self._request.write(data)
            if data.endswith("\r\n\r\n"):
                self._do_handshake()

    def _message_write_cb(self, stream, result, callback):
        written = stream.write_bytes_finish(result)
        if callback:
            callback(written)
 
    def send_message(self, message, callback=None, binary=False):
        protocol_message = protocol.make_message(message)

        stream = self._connection.get_output_stream()
        stream.write_bytes_async(GLib.Bytes.new(protocol_message),
                                 GLib.PRIORITY_DEFAULT,
                                 None, self._message_write_cb, callback)


class Server(GObject.GObject):
    session_started = GObject.Signal("session-started", arg_types=(object,))

    def _input_data_cb(self, session):
        session.got_data()
        return True

    def _incoming_connection_cb(self, service, connection, user_data):
        session = Session(connection)
        self.session_started.emit(session)

        input_stream = connection.get_input_stream()
        source = Gio.PollableInputStream.create_source(input_stream, None)
        source.set_callback(self._input_data_cb, session)
        source.attach()

    def start(self):
        service = Gio.SocketService()
        service.connect("incoming", self._incoming_connection_cb)
        return service.add_any_inet_port(None)


if __name__ == "__main__":
    def message_received_cb(session, message):
        session.send_message(message.data)

    def session_started_cb(server, session):
        session.connect("message-received", message_received_cb)

    server = Server()
    server.connect("session-started", session_started_cb)
    port = server.start()

    print "Listening on port %d" % port

    main_loop = GLib.MainLoop()
    main_loop.run()

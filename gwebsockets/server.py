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

import protocol


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


class Server():
    def __init__(self, address, port):
        self._address = address
        self._port = port
        self._connection = None
        self._request = StringIO()
        self._message = MessageBuffer()
        self._parse_g = None

    def _response_write_cb(self, stream, result, connection):
        stream.write_bytes_finish(result)
        self._connection = connection

    def _do_handshake(self, connection):
        self._request.seek(0)
        response = protocol.make_handshake(self._request)

        stream = connection.get_output_stream()
        stream.write_bytes_async(GLib.Bytes.new(response.encode("utf-8")),
                                 GLib.PRIORITY_DEFAULT,
                                 None, self._response_write_cb, connection)

    def _input_data_cb(self, connection):
        stream = connection.get_input_stream()
        data = stream.read_bytes(8192, None).get_data()

        if self._connection:
            self._message.append(data)
            if self._parse_g is None:
                self._parse_g = protocol.parse_message(self._message)

            parsed_message = self._parse_g.next()
        else:
            self._request.write(data)
            if data.endswith("\r\n\r\n"):
                self._do_handshake(connection)

        return True

    def _incoming_connection_cb(self, service, connection, user_data):
        input_stream = connection.get_input_stream()
        source = Gio.PollableInputStream.create_source(input_stream, None)
        source.set_callback(self._input_data_cb, connection)
        source.attach()

    def _message_write_cb(self, stream, result, callback):
        written = stream.write_bytes_finish(result)
        if callback:
            callback(written)
 
    def send_message(self, message, callback=None):
        stream = self._connection.get_output_stream()
        stream.write_bytes_async(GLib.Bytes.new(message),
                                 GLib.PRIORITY_DEFAULT,
                                 None, self._message_write_cb, callback)

    def start(self):
        inet_address = Gio.InetAddress.new_from_string(self._address)
        socket_address = Gio.InetSocketAddress.new(inet_address, self._port)

        service = Gio.SocketService()
        service.add_address(socket_address, Gio.SocketType.STREAM,
                            Gio.SocketProtocol.TCP, None)

        service.connect("incoming", self._incoming_connection_cb)


if __name__ == "__main__":
    server = Server("127.0.0.1", 9000)
    server.start()

    main_loop = GLib.MainLoop()
    main_loop.run()

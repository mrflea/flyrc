#!/usr/bin/python

# flyrc:
# Loosely based upon geventirc (https://github.com/gwik/geventirc)

import gevent
import gevent.pool
from gevent import queue, socket
from flyrc import handler, message, util
from time import time

# Client events: connected, disconnected, error, global_send, global_recv, load, unload
# (client event names are prefixed with client_)
# 'connected' fires when the client connects to the IRC server.
# 'disconnected' fires when the client's socket closes.
# 'error' fires when the socket generates an error.
# 'global_send' fires any time a message is sent.
# 'global_recv' fires any time a message is received.
# 'load' fires when the handler is loaded (note: only the loading handler's 'load' will be triggered)
# 'unload' fires when the handler is unloaded (note: only the unloading handler's 'unload' will be triggered)

class ClientError(Exception):
	"""A generic flyrc client error."""

class DuplicateHandlerObject(ClientError):
	"""Exception raised when an already-added handler is added a
	second time.

	Attributes:
		obj - the object itself.
	"""
	def __init__(self, obj):
		self.obj = obj

class MissingHandlerObject(ClientError):
	"""Exception raised when attempting to remove a handler that isn't
	loaded.

	Attributes:
		obj - the object itself.
	"""
	def __init__(self, obj):
		self.obj = obj

class DependencyViolation(ClientError):
	"""Exception raised when adding or removing a handler causes a
	dependency violation of some kind.

	Attributes:
		args - the object subject to the conflict.
	"""

class UnsatisfiedDependency(DependencyViolation):
	"""Exception raised when a dependency isn't satisfied.

	Attributes:
		args - the missing dependency.
	"""

class LingeringDependency(DependencyViolation):
	"""Exception raised when a handler being unloaded still has
	dependencies.

	Attributes:
		args - the handler being unloaded.
	"""

class InvalidDependencyTree(DependencyViolation):
	"""Exception raised when the dependency tree has become invalid
	(probably due to prior Dependency exceptions.)

	Attributes:
		args - the handler with invalid dependency information.
	"""

class Client(object):
	def __init__(self, host, port, ssl=False, timeout=300, source=None):
		self._rqueue = queue.Queue()
		self._squeue = queue.Queue()
		self.host = host
		self.port = port
		self.ssl = ssl
		self._timeout = timeout
		self._source = source or ''
		self._socket = None
		self._group = gevent.pool.Group()
		self._coregroup = gevent.pool.Group()

		self._handlers = {}
		self._handlerobjects = {}

		self.throttle_delay = 2
		self.throttle_burst = 5

		self.enforce_order = False

	def _create_socket(self):
		sock = gevent.socket.create_connection((self.host, self.port), source_address=(self._source, 0))
		if self.ssl:
			sock = gevent.ssl.wrap_socket(sock)

		sock.setblocking(1)
		sock.settimeout(self._timeout)

		return sock

	def _ioerror(self, e, step):
		self.stop()
		self._rqueue.put(message.Error(e, step))

	@property
	def timeout(self):
		"""The TCP socket's timeout."""
		return self._timeout

	@timeout.setter
	def timeout(self, t):
		self._timeout = t
		self._socket.settimeout(self._timeout)

	def start(self):
		try:
			self._socket = self._create_socket()
		except socket.error, e:
			self._ioerror(e, message.Step.CONNECT)
		else:
			self._coregroup.spawn(self._send_loop)
			self._coregroup.spawn(self._recv_loop)
			self._handle('client_connected')
		self._coregroup.spawn(self._process_loop)

	def stop(self):
		if self._socket:
			self._socket.close()
			self._socket = None

		self._handle('client_disconnected')

	def shutdown(self):
		self.stop()
		self._coregroup.kill()
		self._rqueue = queue.Queue()
		self._squeue = queue.Queue()

	def join(self):
		self._coregroup.join()
		self._group.join()

	def _send_loop(self):
		buf = ''
		burst_remaining = self.throttle_burst * 1.0
		last_message = 0
		while True:
			msg = self._squeue.get()
			buf += msg.render().encode('utf-8', 'replace') + '\r\n'
			try:
				self._socket.sendall(buf)
				buf = ''
			except socket.error, e:
				print "I/O error in SEND: " + str(e)
				self._ioerror(e, message.Step.SEND)
			except AttributeError:
				# Socket closed, exit.
				return

			# Do throttling, but only if throttle_delay != 0.
			if self.throttle_delay:
				# Add any owed slots.
				if last_message:
					burst_remaining += (time() - last_message) / self.throttle_delay
					if (burst_remaining > self.throttle_burst):
						burst_remaining = self.throttle_burst * 1.0

				# Penalize for the message that was just sent.
				last_message = time()
				burst_remaining -= 1

				# Sleep if we're out of burst.
				if burst_remaining < 1:
					gevent.sleep(self.throttle_delay)
			else:
				gevent.sleep(0)

	def _process_loop(self):
		while True:
			if self.enforce_order:
				self._group.join()
			msg = self._rqueue.get()
			if hasattr(msg, 'e'):
				self._handle('client_error', msg)
			else:
				self._handle_recv(msg)

	def _recv_loop(self):
		buf = ''
		while True:
			try:
				buf += self._socket.recv(4096)
			except socket.error, e:
				print "I/O error in RECV: " + str(e)
				self._ioerror(e, message.Step.RECV)
			except AttributeError:
				# Socket has been closed, exit.
				return
			else:
				lines = buf.split('\r\n')
				buf = lines.pop()
				for line in lines:
					self._rqueue.put(message.Message.parse(line))
			gevent.sleep(0)

	def dependency_satisfier(self, dep):
		for item in self._handlerobjects.keys():
			if isinstance(item, dep):
				return item
		return None

	def add_handler(self, handler):
		if handler in self._handlerobjects.keys():
			raise DuplicateHandlerObject(item)

		dependencies, h_funcs = util.get_handler_properties(handler)
		for dep in dependencies:
			sat = self.dependency_satisfier(dep)
			if not sat:
				raise UnsatisfiedDependency(dep)
			else:
				# Increment refcount.
				self._handlerobjects[sat] += 1

		self._handlerobjects[handler] = 0

		for h_name in h_funcs.iterkeys():
			if self._handlers.has_key(h_name):
				self._handlers[h_name].add(h_funcs[h_name])
			else:
				self._handlers[h_name] = set([h_funcs[h_name]])

		# Special - spawn just this instance, not all "client_load" handlers.
		if h_funcs.has_key('client_load'):
			self._group.spawn(h_funcs['client_load'], self)

	def remove_handler(self, handler):
		if handler not in self._handlerobjects.keys():
			raise MissingHandlerObject(handler)

		if self._handlerobjects[handler] > 0:
			raise LingeringDependency(handler)

		del self._handlerobjects[handler]

		dependencies, h_funcs = util.get_handler_properties(handler)
		for dep in dependencies:
			sat = self.dependency_satisfier(dep)
			if not sat:
				raise InvalidDependencyTree(dep)
			else:
				# Decrement refcount.
				self._handlerobjects[sat] -= 1
				if self._handlerobjects[sat] < 0:
					raise InvalidDependencyTree(sat)

		for h_name in h_funcs.iterkeys():
			self._handlers[h_name] -= set([h_funcs[h_name]])
			# If there aren't any handler functions left, remove that event entirely.
			if not self._handlers[h_name]:
				del self._handlers[h_name]

		# Special - spawn just this instance of client_unload.
		if h_funcs.has_key('client_unload'):
			self._group.spawn(h_funcs['client_unload'], self)

	def _handle(self, hname, *args, **kwargs):
		if self._handlers.has_key(hname):
			for handler in self._handlers[hname]:
				self._group.spawn(handler, self, *args, **kwargs)

	def _handle_recv(self, message):
		self._handle('client_global_recv', message)
		self._handle(message.command.upper(), message)

	def send(self, message):
		self._handle('client_global_send', message)
		self._squeue.put(message)

	def trigger_handler(self, handler, *args, **kwargs):
		self._handle(handler, *args, **kwargs)

	def get_handled_events(self):
		return self._handlers.keys()

# A simple client that can stay connected to an IRC network and supports NickServ/SASL authentication.
class SimpleClient(Client):
	def __init__(self, nick, user, gecos, host, port, ssl=False, timeout=300, autoreconnect=False, version=None, source=None):
		super(SimpleClient, self).__init__(host, port, ssl, timeout, source)

		self.add_handler(handler.Ping())
		self.add_handler(handler.User(nick, user, gecos))
		self.add_handler(handler.NickInUse())
		self.add_handler(handler.MessageProcessor())

		if autoreconnect:
			self.add_handler(handler.AutoReconnect())
		else:
			self.add_handler(handler.GenericDisconnect())

		if version:
			self.add_handler(handler.BasicCTCP(version))
		else:
			self.add_handler(handler.BasicCTCP())

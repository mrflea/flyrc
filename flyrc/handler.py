from flyrc import message, util
import base64
import re

class Ping(object):
	def irc_PING(self, client, msg):
		client.send(message.pong(msg.args[0]))

class AutoJoin(object):
	def __init__(self, *args):
		self.channels = args

	def irc_RPL_WELCOME(self, client, msg):
		for channel in self.channels:
			client.send(message.join(channel))

class NickInUse(object):
	def irc_ERR_NICKNAMEINUSE(self, client, msg):
		client.nick = msg.args[1] + '_'
		client.send(message.nick(client.nick))

	irc_ERR_NICKCOLLISION = irc_ERR_NICKNAMEINUSE

class CAP(object):
	def irc_client_load(self, client):
		self.req = set([])
		self.interactive = set([])
		self.pending = set([])
		self.ack = set([])
		self.rej = set([])

	def irc_client_connect(self, client):
		self.pending = set([])
		self.ack = set([])
		self.rej = set([])

	irc_client_disconnect = irc_client_connect

	def irc_client_connected(self, client):
		if self.req or self.interactive:
			client.send(message.cap('LS'))

	def irc_cap_request(self, client, cap):
		self.req |= set([cap.lower()])

	def irc_cap_request_interactive(self, client, cap):
		self.interactive |= set([cap.lower()])

	def irc_cap_request_remove(self, client, cap):
		self.req -= set([cap.lower()])

	def irc_cap_request_interactive_remove(self, client, cap):
		self.interactive -= set([cap.lower()])

	def irc_cap_interactive_finished(self, client, cap):
		self.pending -= set([cap.lower()])
		self.try_end(client)

	def try_end(self, client):
		if not self.pending:
			client.send(message.cap('END'))

	def irc_CAP(self, client, msg):
		caps = set(msg.args[2].lower().split())
		if msg.args[1] == "LS":
			sought = (self.req | self.interactive)
			unavailable = sought - caps
			for cap in unavailable:
				client.trigger_handler('cap_denied_'+cap)
			client.send(message.cap('REQ', ' '.join(sought - unavailable)))
		if msg.args[1] == "ACK":
			client.cap_acknowledged = caps
			for cap in caps:
				client.trigger_handler('cap_acknowledged_'+cap)
				if cap in self.interactive:
					self.pending |= set([cap])
			self.try_end(client)
		if msg.args[1] == "NAQ":
			client.cap_denied |= caps
			for cap in caps:
				client.trigger_handler('cap_denied_'+cap)
			self.try_end(client)

class SASLPlain(object):
	DEPENDENCIES = [CAP]

	def __init__(self, user, password):
		self.auth = base64.b64encode("%s\0%s\0%s" % (user, user, password))

	def irc_client_load(self, client):
		client.trigger_handler('cap_request_interactive', 'sasl')

	def irc_client_unload(self, client):
		client.trigger_handler('cap_request_interactive_remove', 'sasl')

	def irc_cap_acknowledged_sasl(self, client):
		client.send(message.authenticate("PLAIN"))

	def irc_AUTHENTICATE(self, client, msg):
		# We only support PLAIN, so we don't have to do much work here...
		client.send(message.authenticate(self.auth))
		client.send(message.cap('END'))

class ISupport(object):
	"""This relies on the server sending RPL_VERSION right before RPL_ISUPPORT."""
	def irc_client_load(self, client):
		client.isupport = {}

	def irc_client_unload(self, client):
		del client.isupport

	irc_RPL_VERSION = irc_client_load

	def irc_RPL_ISUPPORT(self, client, msg):
		tokens = msg.args[1:-1]
		for token in tokens:
			token = token.split('=', 1)
			value = True
			if len(token) == 2:
				token, value = token
			else:
				token = token[0]
			token = token.upper()
			# TODO: parse value to make it more useful.
			client.isupport[token] = value

class User(object):
	def __init__(self, nick, user, gecos):
		self.nick = nick
		self.user = user
		self.gecos = gecos

	def irc_client_connected(self, client):
		client.send(message.user(self.user, '*', '*', self.gecos))
		client.send(message.nick(self.nick))
		client.nick = self.nick
		client.user = self.user
		client.gecos = self.gecos

class LogToConsole(object):
	def irc_client_connected(self, client):
		print "Connected to server."

	def irc_client_global_send(self, client, msg):
		print "<< %s" % msg.render()

	def irc_client_global_recv(self, client, msg):
		print ">> %s" % msg.render()

	def irc_client_disconnected(self, client):
		print "Disconnected from server."

	def irc_client_error(self, client, err):
		print "ERROR: %s" % repr(err)

class GenericDisconnect(object):
	def irc_ERROR(self, client, message):
		client.shutdown()

	def irc_client_error(self, client, err):
		client.shutdown()

class Oper(object):
	def __init__(self, user, password):
		self.user = user
		self.password = password

	def irc_RPL_WELCOME(self, client, msg):
		client.send(message.oper(self.user, self.password))

	# Disable throttling because we're opered.
	def irc_RPL_YOUREOPER(self, client, msg):
		client.throttle_delay = 0

class MessageProcessor(object):
	DEPENDENCIES = [User]

	def irc_PRIVMSG(self, client, message):
		ctcp = util.parse_ctcp(message.args[1])
		if ctcp:
			ctcp_args = None
			if len(ctcp) > 1:
				ctcp_args = ctcp[1]
			if ctcp[0] == "ACTION":
				if util.is_nick(message.args[0]):
					client.trigger_handler('private_action', message.source, ctcp_args)
				else:
					client.trigger_handler('channel_action', message.source, message.args[0], ctcp_args)
			else:
				#client.trigger_handler('ctcp_request', message.source, message.args[0], ctcp[0], ctcp_args)
				client.trigger_handler('ctcp_request_'+ctcp[0].upper(), message.source, message.args[0], ctcp_args)
		else:
			if util.is_channel(message.args[0]):
				client.trigger_handler('channel_message', message.source, message.args[0], message.args[1])
			else:
				client.trigger_handler('private_message', message.source, message.args[1])

	def irc_NOTICE(self, client, message):
		ctcp = util.parse_ctcp(message.args[1])
		if ctcp:
			ctcp_args = None
			if len(ctcp) > 1:
				ctcp_args = ctcp[1]
			client.trigger_handler('ctcp_reply', message.source, message.args[0], ctcp[0], ctcp_args)
			client.trigger_handler('ctcp_reply_'+ctcp[0].upper(), message.source, message.args[0], ctcp_args)
		else:
			if util.is_server(message.source.nick):
				client.trigger_handler('server_notice', message.source.nick, message.args[1])
			if util.is_channel(message.args[0]):
				client.trigger_handler('channel_notice', message.source, message.args[0], message.args[1])
			else:
				client.trigger_handler('private_notice', message.source, message.args[1])

class BasicCTCP(object):
	DEPENDENCIES = [MessageProcessor]

	def __init__(self, version="flyrc 0.1"):
		self.version = version

	def irc_ctcp_request_CLIENTINFO(self, client, source, target, args):
		all_handlers = client.get_handled_events()
		ctcps = []
		for handler in all_handlers:
			if handler[:13] == "ctcp_request_":
				h = handler[13:]
				ctcps.append(h)
		client.send(message.notice(source.nick, util.ctcp("CLIENTINFO", ' '.join(ctcps))))

	def irc_ctcp_request_VERSION(self, client, source, target, args):
		client.send(message.notice(source.nick, util.ctcp("VERSION", self.version)))

	def irc_ctcp_request_PING(self, client, source, target, args):
		if args:
			client.send(message.notice(source.nick, util.ctcp("PING", args)))
		else:
			client.send(message.notice(source.nick, util.ctcp("PING")))

class BasicCommand(object):
	"""Base class to use for handlers that provide command signals."""

class BasicChannelCommand(BasicCommand):
	DEPENDENCIES = [MessageProcessor]

	def __init__(self, prefix='!'):
		self.prefix = re.escape(prefix)

	def irc_channel_message(self, client, source, target, text):
		match = re.match("^" + self.prefix + "([^ ]+) ?(.*)", text)
		if not match:
			match = re.match("^" + re.escape(client.nick) + "[:,] ([^ ]+) ?(.*)", text)
		if match:
			cmd = match.group(1).lower()
			args = match.group(2)
			client.trigger_handler('global_command', cmd, source, target, args)
			client.trigger_handler('command_'+cmd, source, target, args)

class BasicPrivateCommand(BasicCommand):
	DEPENDENCIES = [MessageProcessor]

	def irc_private_message(self, client, source, text):
		match = re.match("^([^ ]+) ?(.*)", text)
		if match:
			cmd = match.group(1).lower()
			args = match.group(2)
			client.trigger_handler('global_command', cmd, source, None, args)
			client.trigger_handler('command_'+cmd, source, None, args)

class QuitWhenAsked(object):
	DEPENDENCIES = [BasicCommand]

	def irc_command_quit(self, client, source, target, args):
		client.send(message.quit("Requested by %s." % source.nick))

class LogCommands(object):
	DEPENDENCIES = [BasicCommand]

	def irc_global_command(self, client, command, source, target, args):
		if not args:
			args = ''
		print "Command: <%s!%s@%s %s> %s %s" % (source.nick, source.user, source.host, target, command, args)

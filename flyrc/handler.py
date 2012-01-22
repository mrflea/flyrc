from flyrc import message, numeric, util
import base64
import re
import time

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

class SASL(object):
	def __init__(self, user, password):
		self.auth = base64.b64encode("%s\0%s\0%s" % (user, user, password))

	def irc_client_connected(self, client):
		client.send(message.cap('LS'))

	def irc_CAP(self, client, msg):
		caps = msg.args[2].upper().split()
		if msg.args[1] == "LS":
			if "SASL" in caps:
				client.send(message.cap('REQ', 'SASL'))
		elif msg.args[1] == "ACK":
			if "SASL" in caps:
				# Send the AUTHENTICATE.
				client.send(message.authenticate("PLAIN"))
		elif msg.args[1] == "NAQ":
			if "SASL" in caps:
				client.send(message.cap('END'))

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
		match = re.match("^([^ ]+ ?(.*)", text)
		if match:
			cmd = match.group(1).lower()
			args = match.group(2)
			client.trigger_handler('global_command', cmd, source, target, args)
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

class InfoTracker(object):
	"""This is half-implemented, you probably shouldn't use it."""
	def irc_client_load(self, client):
		client.users = {}
		client.channels = {}
		client.infotracker_pwcstash = {}

	def irc_client_unload(self, client):
		del client.users
		del client.channels
		del client.infotracker_pwcstash

	@staticmethod
	def make_new_user():
		u = {
			'nickname': '',
			'username': '',
			'hostname': '',
			'realname': '',
			'server': '',
			'ssl': False,
			'channels': set([]),
			'account': None,
			'oper': False,
			'signon': None,
			'idle': None,
			'synced': False,
			'last-update': time.time()
		}
		return u

	@staticmethod
	def make_new_channel():
		c = {
			'name': '',
			'topic': '',
			'modes': '',
			'bans': [],
			'quiets': [],
			'ban-exempts': [],
			'invite-exempts': [],
			'users': set([]),
			'voices': set([]),
			'halfops': set([]),
			'ops': set([]),
			'admins': set([]),
			'founders': set([]),
			'synced': False,
			'last-update': time.time()
		}
		return c

	@staticmethod
	def add_user(client, user):
		if not client.users.has_key(user):
			client.users[user] = self.make_new_user()
			client.users[user]['nickname'] = user

	@staticmethod
	def add_channel(client, chan):
		if not client.channels.has_key(chan):
			client.channels[chan] = self.make_new_channel()
			client.channels[chan]['name'] = chan

	@staticmethod
	def remove_channel_status(client, chan, nick):
		user = client.users[nick]
		client.channels[chan]['voices'].discard(user)
		client.channels[chan]['halfops'].discard(user)
		client.channels[chan]['ops'].discard(user)
		client.channels[chan]['admins'].discard(user)
		client.channels[chan]['founders'].discard(user)

	@staticmethod
	def add_user_to_channel(client, chan, nick):
		client.channels[chan]['users'].add(client.users[nick])
		client.users[nick]['channels'].add(client.channels[chan])

	@staticmethod
	def remove_user_from_channel(client, chan, nick):
		remove_channel_status(client, chan, nick)
		client.channels[chan]['users'].discard(client.users[nick])
		client.users[nick]['channels'].discard(client.channels[chan])

	def irc_RPL_WHOISUSER(self, client, msg):
		nick, user, host = msg.args[1:3]
		rn = msg.args[5]
		add_user(client, nick)
		client.users[nick]['username'] = user
		client.users[nick]['hostname'] = host
		client.users[nick]['realname'] = rn

	def irc_RPL_WHOISCHANNELS(self, client, msg):
		nick, channels = msg.args[1:2]
		channels = set(channels.split())
		if client.infotracker_pwcstash.has_key(nick):
			client.infotracker_pwcstash[nick] |= channels
		else:
			client.infotracker_pwcstash[nick] = channels

	def irc_RPL_WHOISSERVER(self, client, msg):
		nick, server = msg.args[1:2]
		client.users[nick]['server'] = server

	# TODO - figure out how to note that this ISN'T present.
	def irc_RPL_WHOISOPERATOR(self, client, msg):
		nick = msg.args[1]
		client.users[nick]['oper'] = True

	# TODO - figure out how to note that this ISN'T present.
	def irc_RPL_WHOISSECURE(self, client, msg):
		nick = msg.args[1]
		client.users[nick]['ssl'] = True

	# TODO - figure out how to note that this ISN'T present.
	def irc_RPL_WHOISLOGGEDIN(self, client, msg):
		nick, acct = msg.args[1:2]
		client.users[nick]['account'] = acct

	# TODO - build a new user object and discard the old one
	# if signon time is different.
	def irc_RPL_WHOISIDLE(self, client, msg):
		nick, idle, signon = msg.args[1:3]
		client.users[nick]['idle'] = int(idle)
		client.users[nick]['signon'] = int(signon)

	def irc_RPL_ENDOFWHOIS(self, client, msg):
		nick = msg.args[1]

		# Change the channel stuff.
		new_channels_obj = set([])
		new_channels = set([])
		if client.infotracker_pwcstash.has_key(nick):
			new_channels = client.infotracker_pwcstash[nick]
			del client.infotracker_pwcstash[nick]

		for channel in channels:
			status = []
			while channel[0] in util.channel_status_map.keys():
				status += util.channel_status_map[channel[0]]
				channel = channel[1:]
			add_channel(client, channel)
			new_channels_obj.add(client.channels[channel])
			client.channels[channel]['users'].add(client.users[nick])
			self.remove_channel_status(client, channel, nick)
			for s in status:
				client.channels[channel][s+'s'].add(client.users[nick])
		removed_channels = client.users[nick]['channels'] - new_channels_obj
		for channel in removed_channels:
			self.remove_user_from_channel(client, channel['name'], nick)
		client.users['nick']['channels'] = new_channels_obj

		# Set last-update and signal the whois_available event.
		client.users[nick]['last-update'] = time.time()
		client.trigger_handler('whois_available', nick)

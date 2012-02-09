from flyrc import util
import time

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

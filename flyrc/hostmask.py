from flyrc import util

def parse_hostmask(text):
	nick = None
	user = None
	host = None
	if text:
		if text.find('!') != -1:
			nick, text = text.split('!', 1)
			user, host = text.split('@', 1)
		else:
			nick = text
	return Hostmask(nick, user, host)

class Hostmask(object):
	def __init__(self, n, u, h):
		self.nick = n
		self.user = u
		self.host = h

	def __str__(self):
		if self.user and self.host:
			return "%s!%s@%s" % (self.nick, self.user, self.host)
		else:
			return self.nick

	def __repr__(self):
		return "<Hostmask(%s, %s, %s)>" % (repr(self.nick), repr(self.user), repr(self.host))

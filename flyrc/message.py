#!/usr/bin/python

from flyrc import hostmask

class ProtocolViolation(Exception):
	def __init__(self, value, position=None):
		self.value = value
		self.position = position

	def __str__(self):
		return "<%s> %s" % (str(self.position), repr(self.value))

class InvalidArgumentOrder(ProtocolViolation):
	"""
	An argument containing spaces was found before
	the end of the argument list, or multiple arguments
	containing spaces were provided.
	"""
	pass

class EmptyArgument(ProtocolViolation):
	"""
	An argument was an empty string.
	"""
	pass

def irc_split(text):
	prefix = None
	command = None
	args = []
	if text:
		trailing = ''
		if text[0] == ':':
			prefix, text = text[1:].split(' ', 1)
		if text.find(' :') != -1:
			text, trailing = text.split(' :', 1)
		args = text.split(' ')
		if trailing:
			args.append(trailing)
		command = args.pop(0)
	return prefix, command, args

def irc_join(prefix, command, args):
	message = ''
	if prefix:
		message += ':' + str(prefix) + ' '
	message += str(command)
	for arg in args:
		if len(arg) == 0:
			continue # shouldn't happen.
		elif arg[0] == ':' or arg.find(' ') != -1:
			message += ' :' + arg
		else:
			message += ' ' + arg
	return message

class Step():
	NONE=0
	SEND=1
	RECV=2
	CONNECT=3

class Message(object):
	@classmethod
	def parse(cls, text):
		prefix, command, args = irc_split(text)
		source = None
		if prefix:
			source = hostmask.Hostmask.parse(prefix)
		return cls(source, command, args)

	def __init__(self, s, c, a):
		self._args = None
		self.source = s
		self.command = c
		self.args = a

	@property
	def args(self):
		return self._args

	@args.setter
	def args(self, newargs):
		for i, arg in enumerate(newargs):
			if i != len(newargs)-1 and (arg[0] == ':' or arg.find(' ') != -1):
				raise InvalidArgumentOrder(arg, i)
		self._args = newargs

	def render(self):
		return irc_join(self.source, self.command, self.args)

	def __repr__(self):
		return "<%s.%s(%s, %s, %s)>" % (type(self).__module__, type(self).__name__, repr(self.source), repr(self.command), repr(self.args))

class Error(object):
	def __init__(self, e, step=Step.NONE):
		self.e = e
		self.step = step

	def __repr__(self):
		return "<%s.%s(%s)>" % (type(self).__module__, type(self).__name__, self.e.__repr__)

def _gen_func(name, command):
	globals()[name] = lambda *args: Message(None, command, list(args))

_functions = [
	'notice',
	'ping',
	'pong',
	'join',
	'user',
	'nick',
	'whois',
	'names',
	'who',
	'whowas',
	'oper',
	'quit',
	'cap',
	'authenticate',
	'mode',
	'topic'
]

for name in _functions:
	_gen_func(name, name.upper())

_gen_func('msg', 'PRIVMSG')

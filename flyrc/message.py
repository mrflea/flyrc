#!/usr/bin/python

from flyrc import hostmask

class ProtocolViolation(Exception):
	def __init__(self, value):
		self.value = value

	def __str__(self):
		return repr(self.value)

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
	for i in range(len(args)):
		if args[i][0] == ':' or args[i].find(' ') != -1:
			if i != len(args)-1:
				raise ProtocolViolation(args[i])
			message += ' :' + args[i]
		else:
			message += ' ' + args[i]
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
		self.source = s
		self.command = c
		self.args = a

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
	'mode'
]

for name in _functions:
	_gen_func(name, name.upper())

_gen_func('msg', 'PRIVMSG')

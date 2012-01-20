#!/usr/bin/python

#from flyrc import message, numeric
import message, numeric

def is_ctcp(text):
	return text[0] == '\001' and text[-1] == '\001'

def parse_ctcp(text):
	if not is_ctcp(text):
		return None
	text = text[1:-1] # strip \001
	return text.split(' ', 1)

def ctcp(*args):
	args = list(args)
	args[0] = args[0].upper()
	cmd = ' '.join(args)
	return "\001%s\001" % cmd

def is_channel(text):
	return not text[0].isalpha()

def is_nick(text):
	return text[0].isalpha() and not is_server(text)

def is_server(text):
	return text.find('.') != -1

def run_client(client):
	client.start()
	graceful_sigint_quit(client)

def graceful_sigint_quit(client):
	exiting = False
	while True:
		try:
			client.join()
			break
		except KeyboardInterrupt:
			if not exiting:
				client.send(message.quit("Keyboard interrupt."))
			else:
				client.shutdown()

def get_handler_properties(h):
	handler_deps = getattr(h, 'DEPENDENCIES', [])
	handler_funcs = {}
	for item in dir(h):
		if item[:4] == "irc_":
			h_name = item[4:]
			func = getattr(h, item)
			if not hasattr(func, '__call__'):
				continue

			h_name = getattr(numeric, h_name, h_name)

			# It shouldn't be possible for a module to add two
			# different handlers for the same event (but
			# technically it is, due to the numerics).
			# We're only going to allow one, however.
			handler_funcs[h_name] = func
	return handler_deps, handler_funcs

channel_status_map = {
	'+': 'voice',
	'%': 'halfop',
	'@': 'op',
	'&': 'admin',
	'~': 'founder'
}

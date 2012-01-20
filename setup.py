from distutils.core import setup

setup(
	name='Flyrc',
	version='0.1.1',
	author='Keith Buck',
	author_email='mr_flea@esper.net',
	packages=['flyrc'],
	url='https://github.com/mrflea/flyrc',
	license='LICENSE.txt',
	description='Fully-featured IRC client library.',
	long_description=open('README.md').read(),
	classifiers=[
		"Development Status :: 3 - Alpha",
		"Intended Audience :: Developers",
		"License :: OSI Approved :: MIT License",
		"Operating System :: OS Independent",
		"Programming Language :: Python",
		"Programming Language :: Python :: 2",
		"Topic :: Communications :: Chat :: Internet Relay Chat",
		"Topic :: Software Development :: Libraries :: Python Modules"
	],
	install_requires=[
		'gevent >= 0.13.6'
	]
)

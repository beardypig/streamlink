`Streamlink <streamlink-website>`_
==================================

|travis-badge|
|codecov-badge|
|backers-badge|
|sponsors-badge|

Streamlink is a CLI utility that pipes flash videos from online
streaming services to a variety of video players such as VLC, or
alternatively, a browser.

The main purpose of Streamlink is to convert CPU-heavy flash plugins to
a less CPU-intensive format.

Streamlink is a fork of the `Livestreamer <https://github.com/chrippa/livestreamer>`__ project.

Please note that by using this application you’re bypassing ads run by
sites such as Twitch.tv. Please consider donating or paying for
subscription services when they are available for the content you
consume and enjoy.

`Installation <streamlink-installation_>`_
==========================================

Installation via Python pip
^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

   sudo pip install streamlink

Manual installation via Python
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

   git clone https://github.com/streamlink/streamlink
   cd streamlink
   sudo python setup.py install

Windows, MacOS, Linux and BSD specific installation methods
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

-  `Windows <streamlink-installation-windows_>`_
-  `Windows portable version <streamlink-installation-windows-portable_>`_
-  `MacOS <streamlink-installation-others_>`_
-  `Linux and BSD <streamlink-installation-linux_>`_

Features
========

Streamlink is built via a plugin system which allows new services to be
easily added.

Supported streaming services, among many others, are:

- `Dailymotion <https://www.dailymotion.com>`_
- `Livestream <https://livestream.com>`_
- `Twitch <https://www.twitch.tv>`_
- `UStream <http://www.ustream.tv>`_
- `YouTube Live <https://www.youtube.com>`_

A list of all supported plugins can be found on the `plugin page <streamlink-plugins_>`_.

Quickstart
==========

After installing, simply use:

::

   streamlink STREAMURL best

Streamlink will automatically open the stream in its default video
player! See `Streamlink’s detailed
documentation <streamlink-documentation_>`_ for all available configuration
options, CLI parameters and usage examples.

Contributing
============

All contributions are welcome. Feel free to open a new thread on the
issue tracker or submit a new pull request. Please read
`CONTRIBUTING.md <CONTRIBUTING.md>`_ first. Thanks!

|opencollective-contributors|

Backers
=======

Thank you to all our backers! [`Become a backer`_]

|opencollective-backers|

Sponsors
========

Support this project by becoming a sponsor. Your logo will show up here
with a link to your website. [`Become a sponsor`_]

|opencollective-sponsor-0|
|opencollective-sponsor-1|
|opencollective-sponsor-2|
|opencollective-sponsor-3|
|opencollective-sponsor-4|
|opencollective-sponsor-5|
|opencollective-sponsor-6|
|opencollective-sponsor-7|
|opencollective-sponsor-8|
|opencollective-sponsor-9|

.. |travis-badge| image:: https://api.travis-ci.org/streamlink/streamlink.svg?branch=master
   :target: https://travis-ci.org/streamlink/streamlink
.. |codecov-badge| image:: https://codecov.io/github/streamlink/streamlink/coverage.svg?branch=master
   :target: https://codecov.io/github/streamlink/streamlink?branch=master
.. |backers-badge| image:: https://opencollective.com/streamlink/backers/badge.svg
   :target: Backers_
.. |sponsors-badge| image:: https://opencollective.com/streamlink/sponsors/badge.svg
   :target: Sponsors_
.. |opencollective-contributors| image:: https://opencollective.com/streamlink/contributors.svg?width=890
.. |opencollective-backers| image:: https://opencollective.com/streamlink/backers.svg?width=890
   :target: https://opencollective.com/streamlink#backers
.. |opencollective-sponsor-0| image:: https://opencollective.com/streamlink/sponsor/0/avatar.svg
   :target: https://opencollective.com/streamlink/sponsor/0/website
.. |opencollective-sponsor-1| image:: https://opencollective.com/streamlink/sponsor/1/avatar.svg
   :target: https://opencollective.com/streamlink/sponsor/1/website
.. |opencollective-sponsor-2| image:: https://opencollective.com/streamlink/sponsor/2/avatar.svg
   :target: https://opencollective.com/streamlink/sponsor/2/website
.. |opencollective-sponsor-3| image:: https://opencollective.com/streamlink/sponsor/3/avatar.svg
   :target: https://opencollective.com/streamlink/sponsor/3/website
.. |opencollective-sponsor-4| image:: https://opencollective.com/streamlink/sponsor/4/avatar.svg
   :target: https://opencollective.com/streamlink/sponsor/4/website
.. |opencollective-sponsor-5| image:: https://opencollective.com/streamlink/sponsor/5/avatar.svg
   :target: https://opencollective.com/streamlink/sponsor/5/website
.. |opencollective-sponsor-6| image:: https://opencollective.com/streamlink/sponsor/6/avatar.svg
   :target: https://opencollective.com/streamlink/sponsor/6/website
.. |opencollective-sponsor-7| image:: https://opencollective.com/streamlink/sponsor/7/avatar.svg
   :target: https://opencollective.com/streamlink/sponsor/7/website
.. |opencollective-sponsor-8| image:: https://opencollective.com/streamlink/sponsor/8/avatar.svg
   :target: https://opencollective.com/streamlink/sponsor/8/website
.. |opencollective-sponsor-9| image:: https://opencollective.com/streamlink/sponsor/9/avatar.svg
   :target: https://opencollective.com/streamlink/sponsor/9/website
.. _Become a backer: https://opencollective.com/streamlink#backer
.. _Become a sponsor: https://opencollective.com/streamlink#sponsor
.. _streamlink-website: https://streamlink.github.io
.. _streamlink-plugins: https://streamlink.github.io/plugin_matrix.html
.. _streamlink-documentation: https://streamlink.github.io/cli.html
.. _streamlink-installation: https://streamlink.github.io/install.html
.. _streamlink-installation-windows: https://streamlink.github.io/install.html#windows-binaries
.. _streamlink-installation-windows-portable: https://streamlink.github.io/install.html#windows-portable-version
.. _streamlink-installation-linux: https://streamlink.github.io/install.html#linux-and-bsd-packages
.. _streamlink-installation-others: https://streamlink.github.io/install.html#other-platforms


# mkdocs-live-edit-plugin

[![PyPI version](https://badge.fury.io/py/mkdocs-live-edit-plugin.svg)](https://pypi.org/project/mkdocs-live-edit-plugin/)  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) ![example workflow](https://github.com/eddyluten/mkdocs-live-edit-plugin/actions/workflows/pylint.yml/badge.svg) [![Downloads](https://pepy.tech/badge/mkdocs-live-edit-plugin)](https://pepy.tech/project/mkdocs-live-edit-plugin)

mkdocs-live-edit-plugin is an MkDocs plugin that allows editing pages directly from the browser.

Things you can do with this plugin when running via `mkdocs serve`:

- Editing a page's Markdown source from the page itself.
- Renaming a page's filename
- Deleting a page
- Creating a brand new page

Some basic editor shortcuts available while editing:

- Ctrl+B/Cmd+B toggles your selection to be **Bold**
- Ctrl+I/Cmd+I toggles your selection to be _Italic_
- Alt+S/Opt+S toggles your selection to be ~~Strikethrough~~
- Ctrl+S/Cmd+S to save your changes

If you like this plugin, you'll probably also like [mkdocs-categories-plugin](https://github.com/EddyLuten/mkdocs-categories-plugin) and [mkdocs-alias-plugin](https://github.com/EddyLuten/mkdocs-alias-plugin).

## Installation

Using Python 3.10 or greater, install the package using pip:

```zsh
pip install mkdocs-live-edit-plugin
```

Then add the following entry to the plugins section of your `mkdocs.yml` file:

```yml
plugins:
  - live-edit
```

## Usage

[![A video showing how to use v0.1.0](https://img.youtube.com/vi/8aUToGfXGVA/0.jpg)](https://www.youtube.com/watch?v=8aUToGfXGVA)

```yml
plugins:
  - live-edit:
      # If, for any reason, you want to override the websocket host and/or port
      # that the Live Edit WebSocket is operating on, you can do so by changing
      # the following options:
      websockets_host: hostname # or any IP or hostname you wish
      websockets_port: 9999 # or any other port you want
      # By default, the plugin doesn't log any information to the browser
      # developer console. To make the output more verbose, set the debug flag:
      debug_mode: true
```

## How Does it Work?

The short answer: [WebSockets](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API) handle client-server communication, while MkDocs handles reloading when files change.

### The Longer Answer

Once installed, when running your local live-reload server, the plugin registers a separate WebSockets server that runs on a specified port. Once your wiki is built, a WebSockets client is installed in your browser, allowing for asynchronous communication between the two.

When you edit the contents of a file in the browser, they are sent to the server via WebSockets, where the plugin writes the contents to disk. Here, MkDocs picks up on the change and sends a reload signal back to the browser -- this is the same live-reload mechanism that picks up on changes you make via a text editor.

A similar mechanism is in place for other operations like renaming and deleting.

## TODO

- Moving pages (also not sure about handling directories here)
- Integration with [mkdocs-categories-plugin](https://github.com/EddyLuten/mkdocs-categories-plugin)
- Integration with [mkdocs-alias-plugin](https://github.com/EddyLuten/mkdocs-alias-plugin)

### Troubleshooting

#### ⚠️ I can't use the plugin from a remote machine

✅ Make sure that MkDocs binds to 0.0.0.0 (the default for MkDocs is 127.0.0.1) by specifying the following flag at startup: `mkdocs serve -a 0.0.0.0:8000`. The plugin will inherit this hostname (unless `websockets_host` is set in the plugin options).

## Changelog

### 0.3.0 (Feb 21, 2025)

**Features and Bug Fixes:**

- Feature: `websocket_host` option for specifiying a hostname other than the one MkDocs uses. If not provided, the plugin uses the same host as your MkDocs config (127.0.0.1 by default).
- Feature: Made the plugin spam the browser console less. This can still be re-enabled by setting `debug_mode` to true in the live-edit section of your config file.
- Bug Fix: unpinned the websocket dependency and upgraded to the current version.
- Bug Fix: fixed incorrect path variable on Chrome on Windows.

### 0.2.1 (Dec 15, 2024)

**Bug fix:** fixes a compatibility issue reported in [#5](https://github.com/EddyLuten/mkdocs-live-edit-plugin/issues/5). This version also pins the websocket dependency to version 13 for the time being since upgrading would be an undertaking outside the scope of a small patch.

### 0.2.0 (Mar 6, 2024)

**New Feature:** Creating pages. The plugin now exposes a button that allows you to create a brand new page from any other page.

### 0.1.5 (Feb 7, 2024)

**Bug fix:** fixes an issue where the WebSocket connection would host on localhost over IPv6. See [#3](https://github.com/EddyLuten/mkdocs-live-edit-plugin/issues/3) for context.

### 0.1.4 (Jan 31, 2024)

**Bug fix:** Improved WebSocket connectivity and error handling. Updated the documentation to match.

### 0.1.3 (Jan 29, 2024)

**Bug fix:** The WebSocket connection now honors the hostname as supplied by the browser in `window.location.hostname`.

### 0.1.2 (Jun 23, 2023)

**Bug fix:** include missing data files

### 0.1.1 (Jun 23, 2023)

**Bug fix:** include non-python files in the package

### 0.1.0 (Jun 23, 2023)

Initial release with editing, renaming, and deletion logic in place.

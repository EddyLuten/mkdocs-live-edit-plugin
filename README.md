# mkdocs-live-edit-plugin

[![PyPI version](https://badge.fury.io/py/mkdocs-live-edit-plugin.svg)](https://pypi.org/project/mkdocs-live-edit-plugin/)  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) ![example workflow](https://github.com/eddyluten/mkdocs-live-edit-plugin/actions/workflows/pylint.yml/badge.svg) [![Downloads](https://pepy.tech/badge/mkdocs-live-edit-plugin)](https://pepy.tech/project/mkdocs-live-edit-plugin)

An MkDocs plugin that allows editing pages directly from the browser.

Things you can do with this plugin when running via `mkdocs serve`:

- Editing a page's Markdown source from the page itself.
- Renaming a page's filename
- Deleting a page

Some basic editor shortcuts available while editing:

- Ctrl+B/Cmd+B toggles your selection to be **Bold**
- Ctrl+I/Cmd+I toggles your selection to be _Italic_
- Alt+S/Opt+S toggles your selection to be ~~Strikethrough~~
- Ctrl+S/Cmd+S to save your changes

If you enjoy this plugin, you may also like these other MkDocs plugins:

- [mkdocs-alias-plugin](https://github.com/EddyLuten/mkdocs-alias-plugin)
- [mkdocs-categories-plugin](https://github.com/EddyLuten/mkdocs-categories-plugin)

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

## TODO

- Creating new pages (not sure how picking directories would work)
- Moving pages (also not sure about handling directories here)
- Integration with [mkdocs-categories-plugin](https://github.com/EddyLuten/mkdocs-categories-plugin)
- Integration with [mkdocs-alias-plugin](https://github.com/EddyLuten/mkdocs-alias-plugin)

## How Does it Work?

The short answer: [WebSockets](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API) handle client-server communication, while MkDocs handles reloading when files change.

### The Longer Answer

Once installed, when running your local live-reload server, the plugin registers a separate WebSockets server that runs on a specified port. Once your wiki is built, a WebSockets client is installed in your browser, allowing for asynchronous communication between the two.

When you edit the contents of a file, they are sent to the server via WebSockets where the plugin writes the contents to disk. Here, MkDocs picks up on the change and sends a reload signal back to the browser -- this is the same live-reload mechanism that picks up on changes you make via a text editor.

A similar mechanism is in place for other operations like renaming and deleting.

## Changelog

### 0.1.0

Initial release with editing, renaming, and deletion logic in place.

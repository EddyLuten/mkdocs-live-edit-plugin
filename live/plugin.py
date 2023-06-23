"""mkdocs-live-edit-plugin

An MkDocs plugin allowing for editing the wiki directly from the browser.
"""

import asyncio
import json
import os
import string
import threading
from logging import Logger, getLogger
from pathlib import Path
from typing import Any, Callable, Literal, Optional

import websockets.client
import websockets.server
from mkdocs.config import config_options
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.livereload import LiveReloadServer
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files
from mkdocs.structure.pages import Page
from websockets.server import serve

_REDIRECT_TEMPLATE_STR = """
<!DOCTYPE html>
<html>
    <head>
        <meta http-equiv="refresh" content="0; url=${new_url}" />
    </head>
</html>
"""
_REDIRECT_TEMPLATE = string.Template(_REDIRECT_TEMPLATE_STR)


class LiveEditPlugin(BasePlugin):
    """
    An MkDocs plugin that allows editing pages directly from the browser.
    """
    config_scheme = (
        ('websockets_port', config_options.Type(int, default=8484)),
    )
    log: Logger = getLogger(f'mkdocs.plugins.{__name__}')
    server_thread: Optional[threading.Thread] = None
    js_contents: Optional[str] = None
    css_contents: Optional[str] = None
    is_serving: bool = False
    mkdocs_config: MkDocsConfig = None
    new_url: str = None

    def __init__(self):
        """Initializes the plugin."""
        parent_dir = Path(__file__).parent
        js_file = parent_dir / 'live-edit.js'
        with open(js_file, 'r', encoding='utf-8') as file:
            self.js_contents = file.read()
        css_file = parent_dir / 'live-edit.css'
        with open(css_file, 'r', encoding='utf-8') as file:
            self.css_contents = file.read()

    def read_file_contents(self, path: str) -> str:
        """Reads the contents of a page from the filesystem."""
        with open(Path(self.mkdocs_config['docs_dir']) / path, 'r', encoding='utf-8') as file:
            return file.read()

    def write_file_contents(self, path: str, contents: str) -> None:
        """Writes the contents of a page to the filesystem."""
        with open(Path(self.mkdocs_config['docs_dir']) / path, 'w', encoding='utf-8') as file:
            file.write(contents)

    def rename_file(self, old_filepath: str, new_filename: str) -> str:
        """Renames a file on the filesystem."""
        try:
            cfg = self.mkdocs_config
            if cfg['docs_dir'] is None:
                raise TypeError('docs_dir is None')
            docs_dir = Path(cfg['docs_dir'])
            old_path = docs_dir / old_filepath
            new_path = old_path.rename(old_path.parent / new_filename)
            new_page = Page(None, File(
                str(new_path.relative_to(docs_dir)),
                cfg['docs_dir'],
                cfg['site_dir'],
                cfg['use_directory_urls']
            ), cfg)
            self.new_url = new_page.canonical_url
            return json.dumps({
                'action':   'rename_file',
                'old_path': str(old_path),
                'new_path': str(new_path),
                'success':  True,
                'new_url':  self.new_url
            })
        except (TypeError, OSError) as error:
            self.log.error(
                'failed to rename %s to %s: %s',
                old_path,
                new_path,
                error
            )
            return json.dumps({
                'action':   'rename_file',
                'success':  False,
                'error':    str(error)
            })

    def delete_file(self, path: str) -> str:
        """Deletes a file on the filesystem."""
        try:
            cfg = self.mkdocs_config
            if cfg['docs_dir'] is None:
                raise TypeError('docs_dir is None')
            docs_dir = Path(cfg['docs_dir'])
            (docs_dir / path).unlink()
            return json.dumps({
                'action':   'delete_file',
                'path':     path,
                'success':  True
            })
        except (TypeError, OSError) as error:
            self.log.error('Error trying to delete %s: %s', path, str(error))
            return json.dumps({
                'action':   'delete_file',
                'path':     path,
                'success':  False,
                'error':    str(error)
            })

    def get_page_contents(self, path: str) -> str:
        """Gets the contents of a page and returns a JSON string describing the result."""
        return json.dumps({
            'action':   'get_contents',
            'path':     path,
            'contents': self.read_file_contents(path)
        })

    def set_page_contents(self, path: str, contents: str) -> str:
        """Sets the contents of a page and returns a JSON string describing the result."""
        try:
            self.write_file_contents(path, contents)
            return json.dumps({
                'action':   'set_contents',
                'path':     path,
                'success':  True,
            })
        except OSError as error:
            self.log.error('failed to write: %s: %s', path, error)
            return json.dumps({
                'action':   'set_contents',
                'path':     path,
                'success':  False,
                'error':    str(error)
            })

    async def websocket_receiver(
        self,
        websocket: websockets.server.WebSocketServerProtocol
    ):
        """The websocket receiver coroutine."""
        self.log.info('live-edit websocket connected')
        while True:
            message = json.loads(await websocket.recv())
            match message['action']:
                case 'get_contents':
                    await websocket.send(
                        self.get_page_contents(message['path'])
                    )
                case 'set_contents':
                    await websocket.send(
                        self.set_page_contents(
                            message['path'],
                            message['contents']
                        )
                    )
                case 'rename_file':
                    await websocket.send(
                        self.rename_file(
                            message['path'],
                            message['new_filename']
                        )
                    )
                case 'delete_file':
                    await websocket.send(
                        self.delete_file(message['path'])
                    )
                case _:
                    await websocket.send(json.dumps({
                        'action':   'error',
                        'message':  f'unknown action {message["action"]}'
                    }))

    async def event_loop(self):
        """The event loop of the websocket server."""
        async with serve(
            self.websocket_receiver,
            "localhost",
            self.config['websockets_port']
        ):
            self.log.info(
                'live-edit websocket server listening on port %s',
                self.config["websockets_port"]
            )
            await asyncio.Future()

    def server_thread_main(self):
        """The main function of the server thread that runs the event loop."""
        self.log.info('live-edit websocket server thread started')
        asyncio.run(self.event_loop())

    def on_startup(self, *, command: Literal['build', 'gh-deploy', 'serve'], dirty: bool) -> None:
        self.is_serving = command == 'serve'

    def error_handler(self, server: LiveReloadServer, code: int) -> bytes | None:
        """Handles errors from the server."""
        # did we recently rename a page and get a 404? redirect to the new page
        if code == 404 and self.new_url is not None:
            self.log.info('redirecting to %s', self.new_url)
            response = _REDIRECT_TEMPLATE.substitute(
                new_url=self.new_url).encode('utf-8')
            self.new_url = None
            return response
        # otherwise, just call the original error handler
        return server.error_handler_orig(code)

    def on_serve(
        self,
        server: LiveReloadServer,
        *,
        config: MkDocsConfig,
        builder: Callable[..., Any]
    ) -> LiveReloadServer | None:
        """Starts the websocket server thread."""
        self.log.info('live-edit websocket server starting')
        # override the server's error handler to handle 404s after a rename
        server.error_handler_orig = server.error_handler
        server.error_handler = lambda code: self.error_handler(server, code)
        self.mkdocs_config = config
        self.server_thread = threading.Thread(
            target=self.server_thread_main,
            daemon=True
        )
        self.server_thread.start()
        return server

    def on_page_content(
        self,
        html: str,
        *,
        page: Page,
        config: MkDocsConfig,
        files: Files
    ) -> str | None:
        """Injects the live-edit script into the page."""
        if not self.is_serving:
            return html
        basename = os.path.basename(Path(page.file.src_path))
        css = f'<style>{self.css_contents}</style>'
        preamble = (
            f"const ws_port = {self.config['websockets_port']};\n"
            f"let page_path = '{page.file.src_path}';\n"
            f"let page_filename = '{basename}';\n"
        )
        return f'{css}\n{html}<script>{preamble}\n{self.js_contents}</script>'

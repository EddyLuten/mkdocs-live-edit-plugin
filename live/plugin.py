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
from typing import Literal, Optional

import websockets.client
import websockets.server
from websockets import serve
from mkdocs.config import config_options
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.livereload import LiveReloadServer
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files
from mkdocs.structure.pages import Page

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
        ('websockets_host', config_options.Type(string, default=None)),
        ('websockets_port', config_options.Type(int, default=8484)),
        ('websockets_timeout', config_options.Type(int, default=10)),
        ('debug_mode', config_options.Type(bool, default=False)),
    )
    log: Logger = getLogger(f'mkdocs.plugins.{__name__}')
    server_thread: Optional[threading.Thread] = None
    js_contents: Optional[str] = None
    css_contents: Optional[str] = None
    is_serving: bool = False
    mkdocs_config: MkDocsConfig = None
    new_url: str = None
    new_page: dict = {
        "created_file": None,
        "new_url": None,
    }

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

    def create_new_file(self, path: str, title: str) -> str:
        """Creates a new file and returns a JSON string describing the result."""
        try:
            new_path = Path(self.mkdocs_config['docs_dir']) / path
            # ensure the parent directory structure exists
            if not new_path.parent.exists():
                new_path.parent.mkdir(parents=True)
            # write the new file
            with open(new_path, 'w', encoding='utf-8') as file:
                file.write(f'# {title}\n\nThis page was created by live-edit.')
            # this new_page is used to redirect the browser to the new page
            # after the next build is complete
            self.new_page["created_file"] = new_path
            return json.dumps({
                'action':   'new_file',
                'path':     path,
                'success':  True
            })
        except OSError as error:
            self.log.error('failed to write: %s: %s', path, error)
            return json.dumps({
                'action':   'new_file',
                'path':     path,
                'success':  False,
                'error':    str(error)
            })

    async def websocket_receiver(
        self,
        websocket: websockets.ServerConnection
    ):
        """The websocket receiver coroutine."""
        self.log.info('live-edit websocket connected')
        await websocket.send(json.dumps({
            'action':   'connected',
            'message':  'live-edit websocket server connected'
        }))
        while True:
            message = None
            try:
                message = json.loads(await websocket.recv())
            except websockets.exceptions.ConnectionClosedOK:
                self.log.info(
                    'live-edit websocket disconnected with status OK'
                )
                break
            except websockets.exceptions.ConnectionClosedError:
                self.log.info(
                    'live-edit websocket disconnected due to an error'
                )
                break
            match message['action']:
                case 'ready':
                    if self.new_page["new_url"] is not None:
                        await websocket.send(
                            json.dumps({
                                'action':   'redirect',
                                'new_url':  self.new_page["new_url"]
                            })
                        )
                        self.new_page["new_url"] = None
                        self.new_page["created_file"] = None
                case 'new_file':
                    await websocket.send(
                        self.create_new_file(
                            message['path'],
                            message['title']
                        )
                    )
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
        host = self.config['websockets_host'] or self.mkdocs_config['dev_addr'].host
        if host is None:
            host = '0.0.0.0' # listen on all interfaces, allow connections from anywhere
        async with serve(
            self.websocket_receiver,
            host,
            self.config['websockets_port']
        ):
            self.log.info(
                'live-edit websocket server listening on %s:%d',
                host,
                self.config['websockets_port']
            )
            await asyncio.Future()

    def server_thread_main(self):
        """The main function of the server thread that runs the event loop."""
        self.log.info('live-edit websocket server thread started')
        asyncio.run(self.event_loop())

    def on_startup(self, *, command: Literal['build', 'gh-deploy', 'serve'], dirty: bool) -> None:
        self.is_serving = command == 'serve'

    def on_pre_page(self, page: Page, /, *, config: MkDocsConfig, files: Files) -> Page | None:
        """Here we try to discern the new URL of a page that was just created."""
        if self.new_page["created_file"] is None or (self.new_page["new_url"] is not None):
            return page
        path = Path(self.mkdocs_config['docs_dir']) / page.file.src_path
        if Path.samefile(path, self.new_page["created_file"]):
            self.log.info('new page created: %s', page.abs_url)
            self.new_page["new_url"] = page.abs_url
        return page

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
        /,
        *,
        config: MkDocsConfig,
        **_
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
        /,
        *,
        page: Page,
        **_
    ) -> str | None:
        """Injects the live-edit script into the page."""
        if not self.is_serving:
            return html
        basename = os.path.basename(Path(page.file.src_path))
        css = f'<style>{self.css_contents}</style>'
        page_base_path = Path(page.file.src_path).parent
        preamble = (
            f"const ws_port = {self.config['websockets_port']};\n"
            f"const debug_mode = {str(self.config['debug_mode']).lower()};\n"
            f"let page_path = '{page.file.src_uri}';\n"
            f"let page_filename = '{basename}';\n"
            f"let page_base_path = '{page_base_path}';\n"
        )
        return f'{css}\n{html}<script>{preamble}\n{self.js_contents}</script>'

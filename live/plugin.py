"""mkdocs-live-edit-plugin

An MkDocs plugin allowing for editing the wiki directly from the browser.
"""

from logging import Logger, getLogger
from pathlib import Path
import threading
import json
from typing import Any, Callable, Literal, Optional

import asyncio
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page
import websockets
from websockets.server import serve

from mkdocs.config import config_options
from mkdocs.plugins import BasePlugin
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.livereload import LiveReloadServer
from mkdocs.structure.files import File

class LiveEditPlugin(BasePlugin):
    """
    Defines the exported MkDocs plugin class and all its functionality.
    """
    config_scheme = (
        ('websockets_port', config_options.Type(int, default=8484)),
    )
    log: Logger = getLogger(f'mkdocs.plugins.{__name__}')
    server_thread: Optional[threading.Thread] = None
    js_contents: Optional[str] = None
    css_contents: Optional[str] = None
    docs_dir: Optional[Path] = None

    def __init__(self):
        js_file = Path(__file__).parent / 'live-edit.js'
        with open(js_file, 'r') as f:
            self.js_contents = f.read()
        css_file = Path(__file__).parent / 'live-edit.css'
        with open(css_file, 'r') as f:
            self.css_contents = f.read()

    def read_file_contents(self, path: str) -> str:
        with open(self.docs_dir / path, 'r') as f:
            return f.read()
        
    def write_file_contents(self, path: str, contents: str) -> None:
        with open(self.docs_dir / path, 'w') as f:
            f.write(contents)

    def get_page_contents(self, path: str) -> str:
        return json.dumps({
            'action':   'get_contents',
            'path':     path,
            'contents': self.read_file_contents(path)
        })
    
    def set_page_contents(self, path: str, contents: str) -> str:
        try:
            self.write_file_contents(path, contents)
            return json.dumps({
                'action':   'set_contents',
                'path':     path,
                'success':  True,
            })
        except Exception as e:
            return json.dumps({
                'action':   'set_contents',
                'path':     path,
                'success':  False,
                'error':    str(e)
            })

    async def websocket_receiver(self, websocket: websockets.WebSocketServerProtocol):
        self.log.info('live-edit websocket connected')
        while True:
            message = json.loads(await websocket.recv())
            match message['action']:
                case 'get_contents':
                    await websocket.send(self.get_page_contents(message['path']))
                case 'set_contents':
                    await websocket.send(self.set_page_contents(message['path'], message['contents']))
                case _:
                    await websocket.send(json.dumps({
                        'action':   'error',
                        'message':  f'unknown action {message["action"]}'
                    }))

    async def event_loop(self):
        async with serve(
            self.websocket_receiver,
            "localhost",
            self.config['websockets_port']
        ):
            self.log.info(f'live-edit websocket server listening on port {self.config["websockets_port"]}')
            await asyncio.Future()

    def server_thread_main(self):
        """The main function of the server thread that runs the event loop."""
        self.log.info('live-edit websocket server thread started')
        asyncio.run(self.event_loop())

    def on_serve(self, server: LiveReloadServer, *, config: MkDocsConfig, builder: Callable[..., Any]) -> LiveReloadServer | None:
        self.docs_dir = Path(config['docs_dir'])
        self.server_thread = threading.Thread(
            target=self.server_thread_main,
            daemon=True
        )
        self.server_thread.start()
    
    def on_page_content(self, html: str, *, page: Page, config: MkDocsConfig, files: Files) -> str | None:
        css = f'<style>{self.css_contents}</style>'
        preamble = f"const page_path = '{page.file.src_path}';"
        return f'{css}\n{html}<script>{preamble}\n{self.js_contents}</script>'

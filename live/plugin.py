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
        ('websockets_port', config_options.Type(int, default=8485)),
        ('websockets_timeout', config_options.Type(int, default=10)),
        ('debug_mode', config_options.Type(bool, default=False)),
        ('article_selector', config_options.Type(string, default=None)),
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
        super().__init__()
        parent_dir = Path(__file__).parent
        js_file = parent_dir / 'live-edit.js'
        with open(js_file, 'r', encoding='utf-8') as file:
            self.js_contents = file.read()
        css_file = parent_dir / 'live-edit.css'
        with open(css_file, 'r', encoding='utf-8') as file:
            self.css_contents = file.read()
        
        # Store reference to the live reload server for triggering rebuilds
        self.livereload_server: LiveReloadServer | None = None
        self.live_reload_server = None

    def read_file_contents(self, path: str) -> str:
        """Reads the contents of a page from the filesystem."""
        with open(Path(self.mkdocs_config['docs_dir']) / path, 'r', encoding='utf-8') as file:
            return file.read()

    def write_file_contents(self, path: str, contents: str) -> None:
        """Writes the contents of a page to the filesystem and triggers rebuild."""
        import time
        import os
        
        start_time = time.time()
        file_path = Path(self.mkdocs_config['docs_dir']) / path
        
        print(f'� [WRITE] Starting file write process')
        print(f'📂 [WRITE] Target file: {file_path}')
        print(f'📊 [WRITE] Content length: {len(contents)} characters')
        print(f'🔍 [WRITE] File exists before write: {file_path.exists()}')
        self.log.info(f'� [WRITE] Starting write to: {file_path} (length: {len(contents)})')
        
        # Check file permissions and directory
        try:
            if file_path.exists():
                file_stats = os.stat(file_path)
                print(f'📋 [WRITE] Current file size: {file_stats.st_size} bytes')
                print(f'⏰ [WRITE] Current file mtime: {file_stats.st_mtime}')
                print(f'🔐 [WRITE] File permissions: {oct(file_stats.st_mode)}')
            
            print(f'📂 [WRITE] Parent directory: {file_path.parent}')
            print(f'📁 [WRITE] Parent exists: {file_path.parent.exists()}')
            print(f'✍️  [WRITE] Writing content to file...')
            
        except Exception as e:
            print(f'⚠️  [WRITE] Could not check file stats: {e}')
        
        # Write the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(contents)
            
        # Verify the write
        new_stats = os.stat(file_path)
        duration = (time.time() - start_time) * 1000
        
        print(f'✅ [WRITE] File written successfully in {duration:.2f}ms')
        print(f'📏 [WRITE] New file size: {new_stats.st_size} bytes')
        print(f'⏰ [WRITE] New file mtime: {new_stats.st_mtime}')
        print(f'🔄 [WRITE] Starting rebuild trigger process...')
        self.log.info(f'✅ [WRITE] File written successfully: {file_path} ({new_stats.st_size} bytes in {duration:.2f}ms)')
        
        # Force filesystem event to trigger MkDocs rebuild
        self._trigger_rebuild_notification(file_path)

    def _trigger_direct_rebuild(self) -> bool:
        """Directly trigger MkDocs rebuild via LiveReloadServer if available."""
        try:
            if self.livereload_server is not None:
                print(f'🎯 [DIRECT_REBUILD] Attempting direct rebuild via LiveReloadServer')
                self.log.info(f'🎯 [DIRECT_REBUILD] Attempting direct rebuild via LiveReloadServer')
                
                # This is the same mechanism used by watchdog file events
                with self.livereload_server._rebuild_cond:
                    print(f'🔄 [DIRECT_REBUILD] Setting _want_rebuild = True')
                    self.livereload_server._want_rebuild = True
                    self.livereload_server._rebuild_cond.notify_all()
                    
                print(f'✅ [DIRECT_REBUILD] Rebuild signal sent successfully')
                self.log.info(f'✅ [DIRECT_REBUILD] Rebuild signal sent successfully')
                
                # Also manually trigger the epoch update for browser reload
                # This ensures the browser gets notified to refresh
                def trigger_browser_reload():
                    import time
                    # Wait for rebuild to potentially complete, then force browser reload signal
                    time.sleep(0.5)  # Give rebuild some time
                    
                    try:
                        # Import the _timestamp function
                        from mkdocs.livereload import _timestamp
                        
                        with self.livereload_server._epoch_cond:
                            # Update the visible epoch to trigger browser reload
                            self.livereload_server._visible_epoch = _timestamp()
                            self.livereload_server._epoch_cond.notify_all()
                            
                        print(f'🌐 [DIRECT_REBUILD] Browser reload signal sent')
                        self.log.info(f'🌐 [DIRECT_REBUILD] Browser reload signal sent')
                        
                    except Exception as e:
                        print(f'⚠️  [DIRECT_REBUILD] Browser reload signal failed: {e}')
                        self.log.warning(f'⚠️  [DIRECT_REBUILD] Browser reload signal failed: {e}')
                
                # Send browser reload signal in background
                import threading
                reload_thread = threading.Thread(target=trigger_browser_reload, daemon=True)
                reload_thread.start()
                
                return True
            else:
                print(f'⚠️  [DIRECT_REBUILD] LiveReloadServer reference not available')
                self.log.warning(f'⚠️  [DIRECT_REBUILD] LiveReloadServer reference not available')
                return False
                
        except Exception as e:
            print(f'❌ [DIRECT_REBUILD] Direct rebuild failed: {e}')
            self.log.error(f'❌ [DIRECT_REBUILD] Direct rebuild failed: {e}')
            return False

    def _trigger_rebuild_notification(self, file_path: Path) -> None:
        """Triggers a rebuild notification for MkDocs file watcher."""
        try:
            import os
            import time
            import threading
            import subprocess
            
            print(f'🔄 [DEBUG] Attempting to trigger rebuild for: {file_path}')
            self.log.info(f'🔄 [DEBUG] Attempting to trigger rebuild for: {file_path}')
            
            # Method 0: Try direct rebuild first (most reliable)
            print(f'🎯 [TRIGGER] Attempting direct rebuild via LiveReloadServer...')
            direct_success = self._trigger_direct_rebuild()
            
            if direct_success:
                print(f'✅ [TRIGGER] Direct rebuild successful - skipping filesystem triggers')
                self.log.info(f'✅ [TRIGGER] Direct rebuild successful - skipping filesystem triggers')
                return
            else:
                print(f'⚠️  [TRIGGER] Direct rebuild failed - falling back to filesystem triggers')
                self.log.warning(f'⚠️  [TRIGGER] Direct rebuild failed - falling back to filesystem triggers')
            
            # Fallback: Use filesystem-based triggers
            # Method 1: Force multiple timestamp updates with delays
            def update_timestamps():
                try:
                    print(f'🕐 [TRIGGER] Starting timestamp updates...')
                    for i in range(3):
                        sleep_time = 0.1 * (i + 1)
                        print(f'⏱️  [TRIGGER] Sleeping {sleep_time*1000:.0f}ms before timestamp update {i+1}/3')
                        time.sleep(sleep_time)  # 100ms, 200ms, 300ms delays
                        
                        old_mtime = os.path.getmtime(file_path)
                        current_time = time.time() + i  # Different timestamps
                        os.utime(file_path, (current_time, current_time))
                        new_mtime = os.path.getmtime(file_path)
                        
                        print(f'✅ [TRIGGER] Timestamp update {i+1}/3 completed: {old_mtime:.3f} -> {new_mtime:.3f}')
                        self.log.info(f'✅ [TRIGGER] Timestamp update {i+1}/3 completed: {old_mtime:.3f} -> {new_mtime:.3f}')
                except Exception as e:
                    print(f'❌ [TRIGGER] Timestamp update failed: {e}')
                    self.log.error(f'❌ [TRIGGER] Timestamp update failed: {e}')
            
            # Method 2: Use Windows 'copy' command to trigger filesystem events
            def trigger_copy_operation():
                try:
                    print(f'📁 [TRIGGER] Starting copy operation trigger...')
                    time.sleep(0.5)  # Wait 500ms
                    print(f'📂 [TRIGGER] Waited 500ms, now executing copy command')
                    
                    # Create a temporary copy and rename it back - this generates filesystem events
                    temp_file = file_path.with_suffix(file_path.suffix + '.tmp')
                    
                    # Use subprocess to run Windows copy command
                    cmd = f'copy "{file_path}" "{temp_file}" >NUL && move "{temp_file}" "{file_path}" >NUL'
                    print(f'💻 [TRIGGER] Executing: {cmd}')
                    
                    result = subprocess.run([
                        'cmd', '/C', cmd
                    ], shell=True, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        print(f'✅ [TRIGGER] Copy operation trigger completed successfully')
                        self.log.info(f'✅ [TRIGGER] Copy operation trigger completed successfully')
                    else:
                        print(f'⚠️  [TRIGGER] Copy operation returned code {result.returncode}')
                        print(f'⚠️  [TRIGGER] stdout: {result.stdout}')
                        print(f'⚠️  [TRIGGER] stderr: {result.stderr}')
                        
                except Exception as e:
                    print(f'❌ [TRIGGER] Copy operation trigger failed: {e}')
                    self.log.error(f'❌ [TRIGGER] Copy operation trigger failed: {e}')
            
            # Method 3: Create and delete trigger files in the docs directory
            def create_trigger_activity():
                try:
                    docs_dir = Path(self.mkdocs_config['docs_dir'])
                    print(f'📝 [TRIGGER] Starting trigger file activity in: {docs_dir}')
                    
                    for i in range(2):
                        sleep_time = 0.3 + (i * 0.1)
                        print(f'⏱️  [TRIGGER] Sleeping {sleep_time*1000:.0f}ms before trigger file {i+1}/2')
                        time.sleep(sleep_time)  # 300ms, 400ms delays
                        
                        trigger_file = docs_dir / f'.live_edit_trigger_{i}'
                        trigger_content = f'rebuild_trigger_{time.time()}_{i}'
                        
                        print(f'📄 [TRIGGER] Creating trigger file: {trigger_file}')
                        # Create trigger file
                        with open(trigger_file, 'w') as f:
                            f.write(trigger_content)
                        
                        print(f'⏸️  [TRIGGER] Brief 50ms pause')
                        time.sleep(0.05)  # Brief pause
                        
                        # Delete trigger file
                        if trigger_file.exists():
                            print(f'🗑️  [TRIGGER] Deleting trigger file: {trigger_file}')
                            os.remove(trigger_file)
                            print(f'✅ [TRIGGER] Trigger file activity {i+1}/2 completed')
                            self.log.info(f'✅ [TRIGGER] Trigger file activity {i+1}/2 completed')
                        else:
                            print(f'⚠️  [TRIGGER] Trigger file {trigger_file} doesn\'t exist for deletion')
                        
                except Exception as e:
                    print(f'❌ [TRIGGER] Trigger file activity failed: {e}')
                    self.log.error(f'❌ [TRIGGER] Trigger file activity failed: {e}')
            
            # Run filesystem-based methods in parallel as fallback
            print(f'🚀 [TRIGGER] Starting filesystem trigger methods in parallel...')
            thread1 = threading.Thread(target=update_timestamps, daemon=True)
            thread2 = threading.Thread(target=trigger_copy_operation, daemon=True) 
            thread3 = threading.Thread(target=create_trigger_activity, daemon=True)
            
            thread1.start()
            thread2.start()
            thread3.start()
            
            print(f'🎯 [TRIGGER] All fallback trigger threads started')
            self.log.info(f'🎯 [TRIGGER] All fallback trigger threads started')
                
        except Exception as e:
            print(f'⚠️  [DEBUG] Could not trigger rebuild notification: {e}')
            self.log.warning(f'⚠️  [DEBUG] Could not trigger rebuild notification: {e}')

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
        import time
        start_time = time.time()
        
        print(f'🎯 [SOCKET] Received set_contents request for: {path}')
        print(f'📊 [SOCKET] Content length: {len(contents)} characters')
        print(f'📋 [SOCKET] Content preview (first 100 chars): {contents[:100]}...')
        self.log.info(f'🎯 [SOCKET] Received set_contents request for: {path} (length: {len(contents)})')
        
        try:
            print(f'📤 [SOCKET] Calling write_file_contents for: {path}')
            self.log.info(f'📤 [SOCKET] Calling write_file_contents for: {path}')
            
            self.write_file_contents(path, contents)
            
            duration = (time.time() - start_time) * 1000  # Convert to milliseconds
            print(f'✅ [SOCKET] set_contents completed successfully in {duration:.2f}ms for: {path}')
            self.log.info(f'✅ [SOCKET] set_contents completed successfully in {duration:.2f}ms for: {path}')
            
            response = json.dumps({
                'action':   'set_contents',
                'path':     path,
                'success':  True,
            })
            print(f'📡 [SOCKET] Sending success response: {response}')
            return response
            
        except OSError as error:
            duration = (time.time() - start_time) * 1000
            print(f'❌ [SOCKET] set_contents FAILED after {duration:.2f}ms for: {path} - Error: {error}')
            self.log.error('❌ [SOCKET] failed to write: %s: %s (after %.2fms)', path, error, duration)
            
            response = json.dumps({
                'action':   'set_contents',
                'path':     path,
                'success':  False,
                'error':    str(error)
            })
            print(f'📡 [SOCKET] Sending error response: {response}')
            return response

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
                raw_message = await websocket.recv()
                print(f'📨 [WEBSOCKET] Received raw message: {raw_message[:200]}...' if len(raw_message) > 200 else f'📨 [WEBSOCKET] Received raw message: {raw_message}')
                self.log.info(f'📨 [WEBSOCKET] Received message length: {len(raw_message)}')
                
                message = json.loads(raw_message)
                print(f'🔍 [WEBSOCKET] Parsed message action: {message.get("action", "unknown")}')
                
                if 'path' in message:
                    print(f'📁 [WEBSOCKET] Target path: {message["path"]}')
                if 'contents' in message:
                    content_length = len(message['contents'])
                    print(f'📊 [WEBSOCKET] Content length: {content_length} characters')
                    print(f'📋 [WEBSOCKET] Content preview: {message["contents"][:150]}...' if content_length > 150 else f'📋 [WEBSOCKET] Content: {message["contents"]}')
                
                self.log.info(f'🔍 [WEBSOCKET] Processing action: {message.get("action", "unknown")}')
                
            except websockets.exceptions.ConnectionClosedOK:
                print(f'👋 [WEBSOCKET] Connection closed normally')
                self.log.info(
                    'live-edit websocket disconnected with status OK'
                )
                break
            except websockets.exceptions.ConnectionClosedError:
                print(f'❌ [WEBSOCKET] Connection closed with error')
                self.log.info(
                    'live-edit websocket disconnected due to an error'
                )
                break
            except json.JSONDecodeError as e:
                print(f'⚠️  [WEBSOCKET] JSON decode error: {e}')
                self.log.error(f'⚠️  [WEBSOCKET] JSON decode error: {e}')
                continue
                
            match message['action']:
                case 'ready':
                    print(f'✅ [WEBSOCKET] Client ready signal received')
                    if self.new_page["new_url"] is not None:
                        redirect_message = json.dumps({
                            'action':   'redirect',
                            'new_url':  self.new_page["new_url"]
                        })
                        print(f'🔄 [WEBSOCKET] Sending redirect: {redirect_message}')
                        await websocket.send(redirect_message)
                        self.new_page["new_url"] = None
                        self.new_page["created_file"] = None
                case 'new_file':
                    print(f'📄 [WEBSOCKET] Creating new file: {message["path"]}')
                    response = self.create_new_file(
                        message['path'],
                        message['title']
                    )
                    print(f'📤 [WEBSOCKET] Sending new_file response: {response}')
                    await websocket.send(response)
                case 'get_contents':
                    print(f'📖 [WEBSOCKET] Getting contents for: {message["path"]}')
                    response = self.get_page_contents(message['path'])
                    print(f'📤 [WEBSOCKET] Sending get_contents response (length: {len(response)})')
                    await websocket.send(response)
                case 'set_contents':
                    import time
                    print(f'💾 [WEBSOCKET] ═══ SAVE OPERATION STARTING ═══')
                    print(f'📁 [WEBSOCKET] Path: {message["path"]}')
                    print(f'📊 [WEBSOCKET] Content length: {len(message["contents"])} characters')
                    print(f'⏰ [WEBSOCKET] Timestamp: {time.strftime("%H:%M:%S")}')
                    
                    response = self.set_page_contents(
                        message['path'],
                        message['contents']
                    )
                    
                    print(f'📤 [WEBSOCKET] Sending set_contents response: {response}')
                    print(f'💾 [WEBSOCKET] ═══ SAVE OPERATION COMPLETED ═══')
                    await websocket.send(response)
                case 'rename_file':
                    print(f'📝 [WEBSOCKET] Renaming file: {message["path"]} -> {message["new_filename"]}')
                    response = self.rename_file(
                        message['path'],
                        message['new_filename']
                    )
                    print(f'📤 [WEBSOCKET] Sending rename_file response: {response}')
                    await websocket.send(response)
                case 'delete_file':
                    print(f'🗑️ [WEBSOCKET] Deleting file: {message["path"]}')
                    response = self.delete_file(message['path'])
                    print(f'📤 [WEBSOCKET] Sending delete_file response: {response}')
                    await websocket.send(response)
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
        
        print(f'🌐 [DEBUG] Preparing WebSocket server on {host}:{self.config["websockets_port"]}')
        self.log.info('🌐 [DEBUG] Preparing WebSocket server on %s:%d', host, self.config['websockets_port'])
        
        try:
            async with serve(
                self.websocket_receiver,
                host,
                self.config['websockets_port']
            ):
                print(f'🎉 [DEBUG] WebSocket server successfully started on {host}:{self.config["websockets_port"]}')
                self.log.info(
                    '🎉 [DEBUG] live-edit websocket server listening on %s:%d',
                    host,
                    self.config['websockets_port']
                )
                await asyncio.Future()
        except Exception as e:
            print(f'💥 [DEBUG] Failed to start WebSocket server: {e}')
            self.log.error('💥 [DEBUG] Failed to start WebSocket server: %s', e)
            raise

    def server_thread_main(self):
        """The main function of the server thread that runs the event loop."""
        print('🎯 [DEBUG] WebSocket server thread started')
        self.log.info('🎯 [DEBUG] live-edit websocket server thread started')
        try:
            print('🔄 [DEBUG] Starting asyncio event loop')
            self.log.info('🔄 [DEBUG] Starting asyncio event loop')
            asyncio.run(self.event_loop())
        except Exception as e:
            print(f'❌ [DEBUG] Error in server thread: {e}')
            self.log.error('❌ [DEBUG] Error in server thread: %s', e)

    def on_config(self, config: MkDocsConfig, **kwargs) -> MkDocsConfig:
        """Armazena configuração para uso posterior"""
        print('📝 [DEBUG] on_config chamado - armazenando configuração')
        self.log.info('📝 [DEBUG] on_config chamado - armazenando configuração')
        self.mkdocs_config = config
        return config

    def on_startup(self, *, command: Literal['build', 'gh-deploy', 'serve'], dirty: bool) -> None:
        print(f'🎯 [DEBUG] LiveEdit on_startup called - command: {command}, dirty: {dirty}')
        self.log.info(f'🎯 [DEBUG] LiveEdit on_startup called - command: {command}, dirty: {dirty}')
        self.is_serving = command == 'serve'
        print(f'🎯 [DEBUG] is_serving set to: {self.is_serving}')
        
        # SOLUÇÃO: Inicia WebSocket server aqui quando detecta modo serve
        if self.is_serving:
            print('🚀 [DEBUG] Iniciando WebSocket server no on_startup (workaround)')
            self.log.info('🚀 [DEBUG] Iniciando WebSocket server no on_startup (workaround)')
            
            # Try to find the LiveReloadServer instance by inspecting the current stack
            # The server should be created shortly after on_startup is called
            def delayed_server_search():
                import gc
                import threading
                import time
                
                print(f'🔍 [DEBUG] Starting delayed search for LiveReloadServer instance...')
                time.sleep(1.5)  # Wait for server to be created
                
                # Search for LiveReloadServer instances in garbage collector
                for obj in gc.get_objects():
                    if isinstance(obj, LiveReloadServer):
                        print(f'🎯 [DEBUG] Found LiveReloadServer instance!')
                        self.livereload_server = obj
                        self.log.info(f'🎯 [DEBUG] LiveReloadServer reference captured successfully')
                        break
                else:
                    print(f'⚠️  [DEBUG] LiveReloadServer instance not found in GC')
                    self.log.warning(f'⚠️  [DEBUG] LiveReloadServer instance not found in GC')
            
            # Start the server search in a background thread
            search_thread = threading.Thread(target=delayed_server_search, daemon=True)
            search_thread.start()
            
            self._start_websocket_server_workaround()

    def _start_websocket_server_workaround(self):
        """Inicia servidor WebSocket como workaround para on_serve não funcionar"""
        try:
            print('🧵 [DEBUG] Criando thread do WebSocket server (workaround)')
            self.log.info('🧵 [DEBUG] Criando thread do WebSocket server (workaround)')
            
            self.server_thread = threading.Thread(
                target=self.server_thread_main,
                daemon=True
            )
            
            print('▶️ [DEBUG] Iniciando thread do WebSocket server (workaround)')
            self.log.info('▶️ [DEBUG] Iniciando thread do WebSocket server (workaround)')
            
            self.server_thread.start()
            
            print('✅ [DEBUG] Thread do WebSocket server iniciada (workaround)')
            self.log.info('✅ [DEBUG] Thread do WebSocket server iniciada (workaround)')
            
        except Exception as e:
            print(f'❌ [DEBUG] Erro ao iniciar WebSocket server: {e}')
            self.log.error(f'❌ [DEBUG] Erro ao iniciar WebSocket server: {e}')

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
        builder,
        **kwargs
    ) -> LiveReloadServer | None:
        """Starts the websocket server thread."""
        print('🚀 [DEBUG] Starting live-edit plugin...')
        self.log.info('🚀 [DEBUG] live-edit websocket server starting')
        self.log.info('🔧 [DEBUG] WebSocket config - host: %s, port: %d', 
                     self.config.get('websockets_host', 'auto'), 
                     self.config.get('websockets_port', 8484))
        
        # override the server's error handler to handle 404s after a rename
        try:
            server.error_handler_orig = server.error_handler
            server.error_handler = lambda code: self.error_handler(server, code)
        except Exception as e:
            print(f'⚠️  [DEBUG] Could not override error handler: {e}')
            
        self.mkdocs_config = config
        
        print('🧵 [DEBUG] Creating WebSocket server thread')
        self.log.info('🧵 [DEBUG] Creating WebSocket server thread')
        self.server_thread = threading.Thread(
            target=self.server_thread_main,
            daemon=True
        )
        print('▶️ [DEBUG] Starting WebSocket server thread')
        self.log.info('▶️ [DEBUG] Starting WebSocket server thread')
        self.server_thread.start()
        print('✅ [DEBUG] WebSocket server thread started successfully')
        self.log.info('✅ [DEBUG] WebSocket server thread started successfully')
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
        page_base_path = Path(page.file.src_path).parent.as_posix()
        preamble = (
            f"const ws_port = {self.config['websockets_port']};\n"
            f"const debug_mode = {str(self.config['debug_mode']).lower()};\n"
            f"let page_path = '{page.file.src_uri}';\n"
            f"let page_filename = '{basename}';\n"
            f"let page_base_path = '{page_base_path}';\n"
        )
        if self.config['article_selector']:
            preamble += f"let article_selector = '{self.config['article_selector']}';\n"
        else:
            preamble += "let article_selector = null;\n"
        return f'{css}\n{html}<script>{preamble}\n{self.js_contents}</script>'

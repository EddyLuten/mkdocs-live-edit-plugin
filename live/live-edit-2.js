(function () {
    const le_log = !debug_mode ? () => { } : (...args) => console.log('live-edit:', ...args);

    le_log('page meta', { page_path, page_filename, page_base_path });

    const websocket_connect = (hostname, port) => {
        return new Promise((resolve, reject) => {
            const totalTries = 3,
                url = `ws://${hostname}:${port}`;
            let tries = totalTries;
            const _getws = () => {
                if (tries <= 0) {
                    reject('Failed to connect to the live-edit server');
                    return;
                }
                --tries;
                le_log(`Connecting to live-edit server at ${url} (try ${totalTries - tries} of ${totalTries})...`);
                let ws = new WebSocket(url);
                ws.onopen = () => resolve(ws);
                ws.addEventListener('error', () => setTimeout(() => _getws(), 1000));
            };
            _getws();
        });
    };
    const
        classes = {
            button: 'live-edit-button',
            controls: 'live-edit-controls',
            editor: 'live-edit-editor',
            hidden: 'live-edit-hidden',
            label: 'live-edit-label',
            wrapper: 'live-edit-wrapper'
        },
        $ = (query, e = document) => e.querySelector(query),
        $$ = (query, e = document) => e.querySelectorAll(query),
        $e = (tag, attrs = {}) => {
            const el = document.createElement(tag);
            for (let [k, v] of Object.entries(attrs)) {
                switch (k) {
                    case 'class':
                        if (Array.isArray(v)) el.classList.add(...v);
                        else el.classList.add(v);
                        break;
                    case 'text': el.innerText = v; break;
                    case 'click': el.addEventListener('click', v); break;
                    case 'html': el.innerHTML = v; break;
                    default: el.setAttribute(k, v); break;
                }
            }
            return el;
        },
        toggle = (el) => el.classList.toggle(classes.hidden),
        hide = (el) => el.classList.add(classes.hidden),
        show = (el) => el.classList.remove(classes.hidden),
        isVisible = (el) => !el.classList.contains(classes.hidden),
        send = (msg) => ws.send(JSON.stringify(msg)),
        events = {};

    const findArticle = () => $('[itemprop="articleBody"]') ?? $('div[role="main"]');
    const registerEvent = (name, handler) => events[name] = handler;
    const dispatchEvent = (name, data) => {
        if (events[name]) events[name](data);
        else le_log('unhandled event', name, data);
    };

    let ws = null,
        wsConnected = websocket_connect(window.location.hostname, ws_port),
        domLoaded = new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve)),
        article = null,
        controls = null,
        editorWrapper = null,
        editor = null,
        editorControls = null;

    const createControls = () => {
        controls = $e('div', { class: classes.controls });
        let _label = $e('span', { text: 'Live Edit', class: classes.label });
        let _edit = $e('button', {
            text: '✏️ Edit',
            class: classes.button,
            title: 'Edit the contents of this page',
            click: (e) => {
                send({ action: 'get_contents', 'path': page_path });
            }
        });
        controls.appendChild(_label);
        controls.appendChild(_edit);
        article.prepend(controls);
    };

    const createEditorControls = () => {
        editorControls = $e('div', { class: [classes.controls] });
        let _label = $e('span', { text: 'Live Edit', class: classes.label });
        let _save = $e('button', {
            text: '💾 Save',
            class: classes.button,
        });
        let _cancel = $e('button', {
            text: '❌ Cancel',
            class: classes.button,
            click: (e) => {
                hide(editorWrapper);
                show(article);
            }
        });
        editorControls.appendChild(_label);
        editorControls.appendChild(_save);
        editorControls.appendChild(_cancel);
        editorWrapper.prepend(editorControls);
    };

    const createEditor = () => {
        // get the classes of the article
        const articleClasses = article.getAttribute('class');
        editorWrapper = $e('div', { class: [classes.wrapper, articleClasses, classes.hidden] });
        editor = $e('div', {
            class: [classes.editor],
            contentEditable: true
        });
        editor.addEventListener('input', () => {
            // log the changes
            le_log('editor input', editor.innerText);
        });
        editor.addEventListener("keydown", (event) => {
            if (event.key !== "Enter") return;
            event.preventDefault(); // Prevent default behavior
            let selection = window.getSelection();
            let range = selection.getRangeAt(0);
            let textNode = range.startContainer;
            let offset = range.startOffset;

            let newline = event.shiftKey ? "\n" : "\n\n"; // Shift+Enter = "\n", Enter = "\n\n"

            // Insert newline at the current cursor position
            if (textNode.nodeType === 3) { // Text node
                let text = textNode.nodeValue;
                let newText = text.slice(0, offset) + newline + text.slice(offset);
                // if the text doesn't end with a newline, add one
                if (!text.endsWith('\n')) newText += '\n';
                textNode.nodeValue = newText;

                // Move cursor after the inserted newline
                range.setStart(textNode, offset + newline.length);
                range.setEnd(textNode, offset + newline.length);
            } else {
                // If not a text node, create a new text node and insert newline
                let newTextNode = document.createTextNode(newline);
                range.insertNode(newTextNode);

                // Move cursor after the new text node
                range.setStart(newTextNode, newline.length);
                range.setEnd(newTextNode, newline.length);
            }

            // Apply the updated cursor position
            selection.removeAllRanges();
            selection.addRange(range);
        });

        // insert the editor after the article
        editorWrapper.appendChild(editor);
        article.parentNode.appendChild(editorWrapper);
        createEditorControls();
    };

    const initialize = (_data) => {
        article = findArticle();
        if (!article) {
            le_log('No article found');
            return;
        }
        createControls();
        createEditor();
        send({ action: 'ready' });
    };

    const onContents = (data) => {
        if (!editor) return;
        editor.innerHTML = data.contents;
        hide(article);
        show(editorWrapper);
    };

    domLoaded.then(() => {
        registerEvent('connected', initialize);
        registerEvent('get_contents', onContents);
        wsConnected.then(_ws => {
            ws = _ws;
            ws.onmessage = (msg) => {
                const data = JSON.parse(msg.data);
                le_log('ws message', data);
                dispatchEvent(data.action, data);
            };
        });
    });
})();

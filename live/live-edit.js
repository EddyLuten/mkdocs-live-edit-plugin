// connect to the specified websocket server. retry 3 times with a 1 second delay
function websocket_connect(hostname, port) {
  return new Promise(function (resolve, reject) {
    const totalTries = 3;
    let tries = totalTries;
    const url = `ws://${hostname}:${port}`;
    const getws = function () {
      if (tries <= 0) {
        reject('Failed to connect to the live-edit server');
        return;
      }
      --tries;
      console.log(`Connecting to live-edit server (try ${totalTries - tries} of ${totalTries})...`);
      let ws = new WebSocket(url);
      ws.onopen = () => resolve(ws);
      ws.addEventListener('error', () => {
        setTimeout(() => getws(), 1000);
      });
    };
    getws();
  });
};

(function () {
  let
    ws = undefined,
    wsConnected = websocket_connect(window.location.hostname, ws_port),
    domLoaded = new Promise(function (resolve) {
      document.addEventListener('DOMContentLoaded', resolve);
    }),
    editButton,
    editSource,
    saveButton,
    cancelButton,
    controls,
    infoModal,
    errorMessageDialog;

  domLoaded.then(() => {
    wsConnected
      .then(wso => {
        console.info('Connected to live-edit server');
        ws = wso;
        ws.onmessage = function (e) {
          let data = JSON.parse(e.data);
          switch (data.action) {
            case 'connected': initialize(data.message); break;
            case 'get_contents': onPageContentsReceived(data); break;
            case 'set_contents': onSavePageContentsReceived(data); break;
            case 'rename_file': onRenamePageReceived(data); break;
            case 'delete_file': onDeletePageReceived(data); break;
            case 'redirect': onRedirectReceived(data); break;
          }
        };
      })
      .catch(e => {
        showErrorMessage(
          `Failed to connect to the live-edit server after several attempts.`
        );
        console.error(e);
      });
  });

  const sendJson = function (data) {
    ws.send(JSON.stringify(data));
  }

  const showError = function (message) {
    errorMessageDialog.innerHTML = message;
    errorMessageDialog.showModal();
  }

  const showInfo = function (message) {
    infoModal.innerHTML = message;
    infoModal.showModal();
  }

  const enterEditMode = function () {
    editButton.classList.add('live-edit-hidden');
    editSource.classList.remove('live-edit-hidden');
    saveButton.classList.remove('live-edit-hidden');
    cancelButton.classList.remove('live-edit-hidden');
  }

  const exitEditMode = function () {
    editButton.classList.remove('live-edit-hidden');
    editSource.classList.add('live-edit-hidden');
    saveButton.classList.add('live-edit-hidden');
    cancelButton.classList.add('live-edit-hidden');
  }

  const onRedirectReceived = function (data) {
    if (data.new_url) {
      showInfo(`Redirecting to: ${data.new_url}`);
      window.location.href = data.new_url;
    }
  }

  const onDeletePageReceived = function (data) {
    if (data.success) {
      showInfo(`Page deleted, waiting on a refresh to 404 from MkDocs...`);
    } else {
      showError(data.error);
    }
  }

  const onRenamePageReceived = function (data) {
    if (data.success) {
      page_path = data.new_path;
      editButton.disabled = false;
      showInfo(
        `Waiting on MkDocs to rebuild and redirect to: ${data.new_url}`
      );
    } else {
      showError(data.error);
    }
  }

  const onSavePageContents = function () {
    saveButton.disabled = true;
    cancelButton.classList.add('live-edit-hidden');
    ws.send(JSON.stringify({
      'action': 'set_contents',
      'path': page_path,
      'contents': editSource.value,
    }));
  }

  const onSavePageContentsReceived = function (data) {
    saveButton.disabled = false;
    if (data.success) {
      editSource.classList.add('live-edit-hidden');
      saveButton.classList.add('live-edit-hidden');
      editButton.classList.remove('live-edit-hidden');
      showInfo('Page saved, waiting on a refresh from MkDocs...');
    } else {
      showError(data.error);
    }
  }

  const onPageContentsReceived = function (data) {
    editButton.disabled = false;
    editButton.classList.add('live-edit-hidden');
    if (editSource) {
      enterEditMode();
      return;
    }

    // add a textbox to the page
    editSource = document.createElement('textarea');
    editSource.innerHTML = data.contents;
    editSource.className = 'live-edit-source';
    editSource.addEventListener('keydown', function (e) {
      const toggleSurroundWithTag = function (tag) {
        e.preventDefault();
        let start = editSource.selectionStart;
        let end = editSource.selectionEnd;
        let text = editSource.value;
        let selectedText = text.substring(start, end);
        let beforeText = text.substring(0, start);
        let afterText = text.substring(end, text.length);
        // text is already surrounded by the tag, remove it.
        if (beforeText.endsWith(tag) && afterText.startsWith(tag)) {
          beforeText = beforeText.substring(0, beforeText.length - tag.length);
          afterText = afterText.substring(tag.length, afterText.length);
          editSource.value = beforeText + selectedText + afterText;
          editSource.selectionStart = start - tag.length;
          editSource.selectionEnd = end - tag.length;
        } else if (selectedText.startsWith(tag) && selectedText.endsWith(tag)) {
          // selection includes the tag, remove it.
          selectedText = selectedText.substring(tag.length, selectedText.length - tag.length);
          editSource.value = beforeText + selectedText + afterText;
          editSource.selectionStart = start;
          editSource.selectionEnd = end - tag.length * 2;
        } else {
          // selection does not include the tag, add it.
          editSource.value = beforeText + tag + selectedText + tag + afterText;
          editSource.selectionStart = start + tag.length;
          editSource.selectionEnd = end + tag.length;
        }
      }
      // bold on ctrl+b
      if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        toggleSurroundWithTag('**');
      }
      // italic on ctrl+i
      if ((e.ctrlKey || e.metaKey) && e.key === 'i') {
        toggleSurroundWithTag('_');
      }
      // strike on alt+s
      if (e.altKey && e.key === 's') {
        toggleSurroundWithTag('~~');
      }
      // save on ctrl+s
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        saveButton.click();
      }
    });
    // add a save button
    saveButton = document.createElement('button');
    saveButton.innerHTML = 'Save';
    saveButton.classList.add('live-edit-button');
    saveButton.classList.add('live-edit-save-button');
    saveButton.addEventListener('click', onSavePageContents);
    // add a cancel button
    cancelButton = document.createElement('button');
    cancelButton.innerHTML = 'Cancel';
    cancelButton.classList.add('live-edit-button');
    cancelButton.classList.add('live-edit-cancel-button');
    cancelButton.addEventListener('click', () => {
      exitEditMode();
      editSource.value = data.contents; // reset the contents
    });
    // add the textbox to the controls
    controls.appendChild(editSource);
    // add the save button after the textbox
    editSource.parentNode.insertBefore(saveButton, editSource.nextSibling);
    // add the cancel button after the save button
    saveButton.parentNode.insertBefore(cancelButton, saveButton.nextSibling);
    enterEditMode();
  }

  const editPage = function () {
    editButton.disabled = true;
    sendJson({
      'action': 'get_contents',
      'path': page_path,
    });
  }

  const renamePage = function () {
    let new_filename = prompt(
      'Enter a new filename for this page',
      page_filename
    );
    if (!new_filename) return;
    if (new_filename === page_filename) {
      return showError(
        'The new filename cannot be the same as the current filename'
      );
    }
    sendJson({
      'action': 'rename_file',
      'path': page_path,
      'new_filename': new_filename,
    });
  }

  const newPage = function () {
    let new_filename = prompt(
      'Enter a filename for the new page. If the parent directory structure ' +
      'does not exist, it will be created.',
      page_base_path + '/untitled.md'
    );
    if (!new_filename) return;
    let new_title = prompt(
      'Enter a title for the new page',
      'Untitled'
    );
    if (!new_filename) return;
    sendJson({
      'action': 'new_file',
      'path': new_filename,
      'title': new_title,
    });
  }

  const addNewButton = function () {
    // add a button
    newButton = document.createElement('button');
    newButton.innerHTML = '📄 New';
    newButton.className = 'live-edit-button align-right';
    newButton.title = 'Create a new page';
    newButton.addEventListener('click', newPage);
    controls.appendChild(newButton);
  }

  const addEditButton = function () {
    // add a button
    editButton = document.createElement('button');
    editButton.innerHTML = '✏️ Edit';
    editButton.className = 'live-edit-button';
    editButton.title = 'Edit the contents of this page';
    editButton.addEventListener('click', editPage);
    controls.appendChild(editButton);
  }

  const addRenameButton = function () {
    // add a button
    renameButton = document.createElement('button');
    renameButton.innerHTML = '📝 Rename';
    renameButton.className = 'live-edit-button';
    renameButton.title = 'Change the filename of this page';
    renameButton.addEventListener('click', renamePage);
    controls.appendChild(renameButton);
  }

  const addDeleteButton = function () {
    // add a button
    deleteButton = document.createElement('button');
    deleteButton.innerHTML = '🗑️ Delete';
    deleteButton.className = 'live-edit-button';
    deleteButton.title = 'Delete this page';
    deleteButton.addEventListener('click', function () {
      if (confirm('Are you sure you want to delete this page?')) {
        sendJson({
          'action': 'delete_file',
          'path': page_path,
        });
      }
    });
    controls.appendChild(deleteButton);
  }

  const addInfoModal = function () {
    infoModal = document.createElement('dialog');
    infoModal.open = false;
    infoModal.classList.add('live-edit-modal');
    infoModal.classList.add('live-edit-info-modal');
    infoModal.addEventListener('click', function () {
      infoModal.close();
    });
    document.body.appendChild(infoModal);
  }

  const addErrorMessageDialog = function () {
    errorMessageDialog = document.createElement('dialog');
    errorMessageDialog.open = false;
    errorMessageDialog.classList.add('live-edit-modal');
    errorMessageDialog.classList.add('live-edit-error-message-dialog');
    errorMessageDialog.addEventListener('click', function () {
      errorMessageDialog.close();
    });
    document.body.appendChild(errorMessageDialog);
  }

  const showErrorMessage = function (message) {
    if (!controls) {
      controls = document.createElement('div');
      controls.className = 'live-edit-controls';
      // add a label to the controls
      label = document.createElement('span');
      label.innerHTML = 'Live Edit:';
      label.className = 'live-edit-label';
      controls.appendChild(label);
      let article = document.querySelector('[itemprop="articleBody"]');
      if (article) {
        article.prepend(controls);
      }
    }
    label.innerHTML = `Live Edit: ${message}`;
  }

  const initialize = function (message) {
    console.info(message);
    domLoaded
      .then(() => {
        controls = document.createElement('div');
        controls.className = 'live-edit-controls';
        // add a label to the controls
        label = document.createElement('span');
        label.innerHTML = 'Live Edit:';
        label.className = 'live-edit-label';
        controls.appendChild(label);
        // add the controls to the page after the H1
        let article = document.querySelector('article');
        if (article) {
          article.prepend(controls);
          addEditButton();
          addRenameButton();
          addDeleteButton();
          addNewButton();
          addInfoModal();
          addErrorMessageDialog();
        }
        sendJson({ 'action': 'ready' });
      })
      .catch((e) => {
        console.error(e);
      });
  };
})();
